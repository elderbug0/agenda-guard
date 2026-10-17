"""LLM stream-window classifier with internal statuses and public binary categories."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.models import Session

log = logging.getLogger("agenda_guard.analyzer")

VALID_STATUSES = {"on_track", "moved_on", "off_track"}

RESULT_SCHEMA = {
    "name": "agenda_check",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": sorted(VALID_STATUSES)},
            "matched_item_id": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["status", "matched_item_id", "confidence", "reason"],
        "additionalProperties": False,
    },
}

PROMPT = """You monitor a meeting against its agenda.

Agenda:
{agenda}

Current item: {current_item}

You get two pieces of transcript: the recent window, and the most recent ~6 seconds.
Decide what the group is talking about NOW, focusing mostly on the most recent ~6 seconds.
- on_track: the discussion is relevant to the current item
- moved_on: it clearly belongs to a different agenda item (return its id)
- off_track: it is unrelated to every agenda item

Rules:
- Answer off_track only when the most recent speech is clearly about a subject unrelated to the agenda (for example food, drinks, sports, weather, personal life).
- Greetings, introductions like "hello everyone" or "I am going to talk about...", filler words and unfinished sentences are on_track.
- If the recent speech mixes the agenda topic with something else, answer on_track.
- Judge by topic, never by who is speaking.
- If you truly cannot tell, answer on_track.
- matched_item_id: the id of the agenda item the discussion belongs to (the current item's id for on_track), or null for off_track.
- confidence: a number from 0 to 1 for how sure you are about the status.
- reason: one short sentence describing what the discussion is about. It is shown to the whole call, so never include a person's name.
Return JSON only."""

_client: Any = None


def _get_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI  # imported lazily so the app can start without a key

        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def build_prompt(session: Session) -> str:
    agenda = "\n".join(
        f"- [{i.id}] {i.title}"
        + (f": {i.description}" if i.description else "")
        + (f" ({i.minutes} min)" if i.minutes else "")
        for i in session.agenda
    )
    current = session.current_item()
    return PROMPT.format(agenda=agenda, current_item=f"[{current.id}] {current.title}")


def normalize(raw: dict, session: Session) -> dict:
    """Make the model output safe for the drift engine."""
    status = raw.get("status")
    if status not in VALID_STATUSES:
        status = "on_track"
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    matched = raw.get("matched_item_id")
    if matched is not None and session.item_by_id(str(matched)) is None:
        matched = None
    if status == "moved_on" and matched is None:
        status = "on_track"  # moved_on needs a real agenda item

    reason = " ".join(str(raw.get("reason", "")).split())[:200]
    return {
        "status": status,
        # A recognized move to another agenda item remains useful internally,
        # but it is on-topic for the user-facing binary stream classification.
        "category": "off_topic" if status == "off_track" else "on_topic",
        "matched_item_id": str(matched) if matched is not None else None,
        "confidence": confidence,
        "reason": reason,
    }


async def analyze(session: Session, text: str | None = None, now: float | None = None) -> dict:
    """Classify the latest transcript window against the agenda."""
    if text is None:
        text = session.text_of_last(settings.WINDOW_S, now)
    # The newest ~10 seconds, so a fresh topic change is not diluted by older sentences.
    recent = session.text_of_last(6, now, settings.STABLE_WORD_DELAY_S) or text
    user_text = f"Recent window:\n{text}\n\nMost recent 6 seconds:\n{recent}"
    resp = await _get_client().chat.completions.create(
        model=settings.ANALYZER_MODEL,
        temperature=0,
        response_format={"type": "json_schema", "json_schema": RESULT_SCHEMA},
        messages=[
            {"role": "system", "content": build_prompt(session)},
            {"role": "user", "content": user_text},
        ],
    )
    try:
        raw = json.loads(resp.choices[0].message.content)
    except (TypeError, ValueError):
        log.warning("Analyzer returned unparseable output; treating the window as on_track")
        raw = {"status": "on_track", "confidence": 0.0, "reason": "unparseable analyzer output"}
    return normalize(raw, session)