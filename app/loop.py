"""Per-session timed-stream classifier and sustained off-topic alarm gate."""
from __future__ import annotations

import asyncio
import logging
import time

from app import drift
from app.analyzer import analyze
from app.config import settings
from app.models import Event, Session
from app.reactor import react
from app.report import build_report, save_report
from app.sessions import store

log = logging.getLogger("agenda_guard.loop")

_tasks: dict[str, asyncio.Task] = {}


async def tick(session: Session, now: float | None = None) -> int | None:
    """Run one analysis window. Returns the alert level that fired, if any."""
    now = time.time() if now is None else now
    session.prune(now)
    if session.words and session.word_version == session.last_analyzed_word_version:
        return None  # do not repeatedly score an unchanged media window
    if session.words and session.pending_word_count < settings.MIN_NEW_WORDS:
        return None  # wait for enough fresh speech to make a meaningful decision
    text = session.text_of_last(settings.WINDOW_S, now, settings.STABLE_WORD_DELAY_S)
    n_words = len(text.split())
    if n_words < settings.MIN_WORDS:
        log.info("Skipped analysis: %d words in the window (need %d)", n_words, settings.MIN_WORDS)
        return None  # silence or near-silence is not a signal either way

    result = await analyze(session, text)
    log.info(
        "Analyzer: status=%s confidence=%.2f reason=%s",
        result["status"], result["confidence"], result["reason"],
    )
    if session.words:
        session.last_analyzed_word_version = session.word_version
        session.pending_word_count = 0
    level = drift.update(session, result, now)
    session.events.append(
        Event(
            ts=now,
            status=result["status"],
            category=result.get("category", "off_topic" if result["status"] == "off_track" else "on_topic"),
            item_id=result.get("matched_item_id") or session.current_item_id,
            confidence=result["confidence"],
            reason=result["reason"],
            alert_level=level,
        )
    )
    if level:
        outcome = await react(session, result, level)
        log.info("Session %s alert level %s sent: %s", session.id, level, outcome)
    return level


async def _run(session_id: str) -> None:
    while True:
        await asyncio.sleep(settings.ANALYSIS_INTERVAL_S)
        session = store.get(session_id)
        if session is None or session.status == "ended":
            return
        if session.status != "active":
            continue  # the bot has not been admitted yet
        try:
            await tick(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Analysis tick failed for session %s", session_id)


def start_loop(session: Session) -> None:
    task = _tasks.get(session.id)
    if task is None or task.done():
        _tasks[session.id] = asyncio.create_task(_run(session.id))


def stop_loop(session_id: str) -> None:
    task = _tasks.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()


async def shutdown_all() -> None:
    tasks = list(_tasks.values())
    for session_id in list(_tasks):
        stop_loop(session_id)
    await asyncio.gather(*tasks, return_exceptions=True)


def end_session(session: Session, reason: str = "ended") -> dict:
    """Stop analysis, mark the session ended, save and return the report. Safe to call twice."""
    if session.status != "ended":
        session.status = "ended"
        session.ended_ts = time.time()
        session.end_reason = reason
        stop_loop(session.id)
        report = build_report(session)
        try:
            save_report(report)
        except Exception:
            log.exception("Could not save report for session %s", session.id)
        return report
    return build_report(session)