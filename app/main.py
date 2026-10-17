"""FastAPI app and routes.

POST /sessions                    create a session (Meet URL + agenda + mode)
GET  /sessions/{id}               live status
POST /sessions/{id}/start         send the bot into the meeting
POST /sessions/{id}/test-alert    fire a test alert (use it to check the sound, Phase 0)
POST /sessions/{id}/end           remove the bot, save and return the report
GET  /sessions/{id}/report        report (live, or the saved one after a restart)
POST /webhooks/recall             Recall.ai callbacks (see webhooks.py)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.analyzer import close_client
from app.config import settings
from app.drift import ALLOWED_SWITCHES
from app.loop import end_session, shutdown_all, start_loop
from app.models import AgendaItem, Session, SessionCreate
from app.reactor import react
from app.recall_client import RecallError, recall
from app.report import build_report, init_db, load_report
from app.sessions import store
from app.webhooks import router as webhook_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agenda_guard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    await shutdown_all()
    await recall.aclose()
    await close_client()


app = FastAPI(title="Agenda Guard", lifespan=lifespan)
app.include_router(webhook_router)


def _get(session_id: str) -> Session:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _require(**values: str) -> None:
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing setting(s) in .env: {', '.join(missing)}")


def _summary(session: Session) -> dict:
    current = session.current_item()
    return {
        "id": session.id,
        "status": session.status,
        "meeting_url": session.meeting_url,
        "bot_id": session.bot_id,
        "agenda": [i.model_dump() for i in session.agenda],
        "current_item": {"id": current.id, "title": current.title},
        "off_track_streak": session.off_track_streak,
        "alert_count": session.alert_count,
        "mode": session.mode,
        "topic": session.topic,
        "switches": session.switches,
        "switches_allowed": ALLOWED_SWITCHES[session.mode],
        "analysis_enabled": settings.ANALYSIS_ENABLED,
        "transcript_segments": len(session.transcript),
        "recent_events": [e.model_dump() for e in session.events[-20:]],
    }


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/sessions", status_code=201)
async def create_session(body: SessionCreate) -> dict:
    agenda: list[AgendaItem] = []
    seen: set[str] = set()
    for index, item in enumerate(body.agenda, start=1):
        item_id = item.id or f"item-{index}"
        if item_id in seen:
            raise HTTPException(status_code=422, detail=f"Duplicate agenda item id: {item_id}")
        seen.add(item_id)
        agenda.append(
            AgendaItem(id=item_id, title=item.title, description=item.description, minutes=item.minutes)
        )

    if body.mode == "high" and len(agenda) != 1:
        raise HTTPException(status_code=422, detail="High mode needs exactly one topic.")
    if not agenda:
        if body.mode != "easy":
            raise HTTPException(
                status_code=422,
                detail="Add a starting topic (only Easy mode can start without one).",
            )
        agenda = [
            AgendaItem(
                id="open",
                title="Open discussion",
                description="No fixed topic. Any subject is fine as long as the talk flows naturally from one subject to the next.",
            )
        ]
        home_id = None
    else:
        if body.start_index >= len(agenda):
            raise HTTPException(status_code=422, detail="start_index is outside the agenda.")
        home_id = agenda[body.start_index].id

    session = store.create(body.meeting_url, agenda)
    session.mode = body.mode
    session.home_item_id = home_id
    session.current_item_id = home_id or agenda[0].id
    session.topic = session.home_title()
    return _summary(session)


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    return _summary(_get(session_id))


@app.get("/sessions/{session_id}/transcript")
async def get_transcript(session_id: str, last: int = 50) -> dict:
    """The most recent transcript segments (the last ~10 minutes are kept in memory)."""
    session = _get(session_id)
    segments = session.transcript[-max(1, last):]
    live = session.partial_words
    return {
         "status": session.status,
         "count": len(segments),
         "segments": [s.model_dump() for s in segments],
         "partial": {"speaker": live[0].speaker, "text": " ".join(w.text for w in live)} if live else None,
    }


@app.post("/sessions/{session_id}/start")
async def start_session(session_id: str) -> dict:
    session = _get(session_id)
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Session already ended")
    if session.bot_id:
        raise HTTPException(status_code=409, detail="Session already started")
    _require(RECALL_API_KEY=settings.RECALL_API_KEY, WEBHOOK_BASE_URL=settings.WEBHOOK_BASE_URL)
    if settings.ANALYSIS_ENABLED:
        _require(OPENAI_API_KEY=settings.OPENAI_API_KEY)
    webhook_url = f"{settings.WEBHOOK_BASE_URL.rstrip('/')}/webhooks/recall"
    try:
        bot_id = await recall.create_bot(session.meeting_url, webhook_url)
    except RecallError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    store.attach_bot(session, bot_id)
    if settings.ANALYSIS_ENABLED:
        start_loop(session)  # analyzes once the bot is admitted and speech arrives
    else:
        log.info("Session %s started in transcript-only mode (ANALYSIS_ENABLED=false)", session.id)
    return _summary(session)


@app.post("/sessions/{session_id}/test-alert")
async def test_alert(session_id: str, level: int = 1) -> dict:
    session = _get(session_id)
    if not session.bot_id:
        raise HTTPException(status_code=409, detail="Start the session first")
    fake = {"status": "off_track", "matched_item_id": None, "confidence": 1.0, "reason": "this is a test alert"}
    outcome = await react(session, fake, 2 if level >= 2 else 1)
    return {"level": 2 if level >= 2 else 1, "outcome": outcome}


@app.post("/sessions/{session_id}/end")
async def end(session_id: str) -> dict:
    session = _get(session_id)
    if session.bot_id and session.status != "ended":
        try:
            await recall.remove_bot(session.bot_id)
        except RecallError as exc:
            log.warning("Could not remove bot for session %s: %s", session_id, exc)
    return end_session(session, "ended_by_host")


@app.get("/sessions/{session_id}/report")
async def get_report(session_id: str) -> dict:
    session = store.get(session_id)
    if session is not None:
        return build_report(session)
    saved = load_report(session_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return saved