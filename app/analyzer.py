"""LLM stream-window classifier: tracks the meeting topic and how it changes."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.models import Session

log = logging.getLogger("agenda_guard.analyzer")

RELATIONS = ["same", "connected", "unrelated"]

RESULT_SCHEMA = {
    "name": "topic_check",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "relation": {"type": "string", "enum": RELATIONS},
            "on_home_topic": {"type": "boolean"},
            "matched_item_id": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["topic", "relation", "on_home_topic", "matched_item_id", "confidence", "reason"],
        "additionalProperties": False,
    },
}

PROMPT = """You monitor a meeting and track how its topic changes.

Home topic (where the meeting started): {home}

Agenda items (for context):
{agenda}

Previous topic (what the group was discussing before): {previous}

You get two pieces of transcript: the recent window, and the most recent ~6 seconds.
Judge what the group is talking about NOW, focusing mostly on the most recent ~6 seconds.

Return:
- topic: a short label (at most 6 words, never a person's name) for what is being discussed now.
- relation: how the current discussion relates to the PREVIOUS topic:
  - same: still the previous topic. This includes details, examples, sub-points, questions about it, greetings, filler words and unfinished sentences.
  - connected: a different topic that follows logically from the previous one, a natural next step or a closely related subject where a listener can see the link.
  - unrelated: an abrupt jump to a subject with no logical link to the previous topic.
- on_home_topic: true if the current discussion is about the home topic (always false when there is no home topic).
- matched_item_id: the id of the agenda item the discussion belongs to, or null.
- confidence: a number from 0 to 1 for how sure you are about the relation.
- reason: one short sentence describing what the discussion is about. It is shown to the whole call, so never include a person's name.

Rules:
- If you are unsure between same and connected, answer same. If you are unsure between connected and unrelated, answer connected.
- If the previous topic is "none yet", answer same.
- Judge by topic, never by who is speaking.
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
        f"- [{i.id}] {i.title}" + (f": {i.description}" if i.description else "")
        for i in session.agenda
    )
    home = session.home_item()
    if home is None:
        home_text = "none (open discussion, there is no fixed starting topic)"
    else:
        home_text = home.title + (f": {home.description}" if home.description else "")
    previous = session.topic or "none yet (the meeting has only just started)"
    return PROMPT.format(home=home_text, agenda=agenda, previous=previous)


def normalize(raw: dict, session: Session) -> dict:
    """Make the model output safe for the drift engine."""
    relation = raw.get("relation")
    if relation not in RELATIONS or not session.topic:
        relation = "same"  # with no previous topic there is nothing to compare with
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    on_home = bool(raw.get("on_home_topic")) and session.home_item() is not None
    matched = raw.get("matched_item_id")
    if matched is not None and session.item_by_id(str(matched)) is None:
        matched = None
    topic = " ".join(str(raw.get("topic", "")).split())[:60]
    reason = " ".join(str(raw.get("reason", "")).split())[:200]

    # Display status for the timeline. drift.py may change it when it applies the mode rules.
    if on_home or relation == "same":
        status = "on_track"
    elif relation == "unrelated":
        status = "off_track"
    else:
        status = "moved_on"
    return {
        "status": status,
        "category": "off_topic" if status == "off_track" else "on_topic",
        "relation": relation,
        "topic": topic,
        "on_home_topic": on_home,
        "matched_item_id": str(matched) if matched is not None else None,
        "confidence": confidence,
        "reason": reason,
    }


async def analyze(session: Session, text: str | None = None, now: float | None = None) -> dict:
    """Classify the latest transcript window against the current topic."""
    if text is None:
        text = session.text_of_last(settings.WINDOW_S, now)
    # The newest few seconds, so a fresh topic change is not diluted by older sentences.
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
        log.warning("Analyzer returned unparseable output; treating the window as the same topic")
        raw = {"relation": "same", "confidence": 0.0, "reason": "unparseable analyzer output"}
    return normalize(raw, session)