"""Recall.ai webhook handler: transcript events and bot status changes."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.loop import end_session
from app.models import TranscriptWord
from app.sessions import store

log = logging.getLogger("agenda_guard.webhooks")
router = APIRouter()

# Bot status events that mean the meeting is over for us.
END_EVENTS = {"bot.call_ended": "call_ended", "bot.done": "done", "bot.fatal": "fatal"}


def verify_signature(headers, body: bytes, secret: str, tolerance_s: int = 300) -> bool:
    """Check a Recall.ai request signature (HMAC-SHA256 over "id.timestamp.body")."""
    msg_id = headers.get("webhook-id") or headers.get("svix-id")
    timestamp = headers.get("webhook-timestamp") or headers.get("svix-timestamp")
    signatures = headers.get("webhook-signature") or headers.get("svix-signature")
    if not (msg_id and timestamp and signatures):
        return False
    try:
        if abs(time.time() - int(timestamp)) > tolerance_s:
            return False
        key = base64.b64decode(secret.removeprefix("whsec_"))
    except ValueError:
        return False
    signed = f"{msg_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    for part in signatures.split():
        version, _, signature = part.partition(",")
        if version == "v1" and hmac.compare_digest(signature, expected):
            return True
    return False


def words_to_text(words: list) -> str:
    parts = (w.get("text", "") for w in words if isinstance(w, dict))
    return " ".join(" ".join(parts).split())


def _timestamp(value: object) -> float | None:
    """Accept Recall numeric timestamps and RFC 3339 timestamps."""
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
    else:
        return None
    return parsed if math.isfinite(parsed) else None


def parse_words(words: list, speaker: str, received_ts: float) -> list[TranscriptWord]:
    """Normalize a webhook word batch; malformed words never poison the stream."""
    parsed: list[TranscriptWord] = []
    for raw in words:
        if not isinstance(raw, dict):
            continue
        text = " ".join(str(raw.get("text", "")).split())
        if not text:
            continue
        start = _timestamp(raw.get("start_timestamp"))
        end = _timestamp(raw.get("end_timestamp"))
        # Maintain backwards compatibility with older Recall payloads while
        # preferring their supplied media timestamps whenever they are present.
        if start is None and end is None:
            start = end = received_ts
        elif start is None:
            start = end
        elif end is None:
            end = start
        if end < start:
            log.warning("Ignoring word with end_timestamp before start_timestamp")
            continue
        parsed.append(
            TranscriptWord(
                speaker=speaker,
                text=text,
                start_timestamp=start,
                end_timestamp=end,
                received_ts=received_ts,
            )
        )
    return parsed


def handle_event(payload: dict, now: float | None = None) -> str:
    """Apply one webhook payload to its session. Returns a short outcome label."""
    event = payload.get("event", "")
    data = payload.get("data") or {}
    bot_id = (data.get("bot") or {}).get("id")
    session = store.get_by_bot(bot_id) if bot_id else None
    if session is None:
        return "ignored: unknown bot"
    if session.status == "ended":
        return "ignored: session ended"

    if event == "transcript.data":
        inner = data.get("data") or {}
        received_ts = time.time() if now is None else now
        speaker = (inner.get("participant") or {}).get("name") or "Unknown"
        words = parse_words(inner.get("words") or [], speaker, received_ts)
        if not words:
            return "ignored: empty transcript"
        added = session.add_words(speaker, words, received_ts)
        if not added:
            return "ignored: duplicate transcript"
        text = " ".join(word.text for word in added)
        if session.status == "waiting":
            session.status = "active"  # first words heard: the bot is in the call
        session.add_segment(speaker, text, received_ts)
        log.info("[transcript %s] %s: %s", session.id, speaker, text)
        return "segment added"

    if event == "bot.in_call_recording":
        if session.status == "waiting":
            session.status = "active"
        return "session active"

    if event in END_EVENTS:
        end_session(session, END_EVENTS[event])
        return "session ended"

    return "ignored: unhandled event"


def _webhook_metadata(payload: dict) -> tuple[str, str | None, int]:
    """Return safe, compact webhook details for the server log."""
    event = str(payload.get("event", ""))
    data = payload.get("data") or {}
    bot_id = (data.get("bot") or {}).get("id")
    inner = data.get("data") or {}
    words = inner.get("words") or []
    return event, str(bot_id) if bot_id else None, len(words) if isinstance(words, list) else 0


@router.post("/webhooks/recall")
async def recall_webhook(request: Request) -> dict:
    body = await request.body()
    if settings.RECALL_WORKSPACE_SECRET and not verify_signature(
        request.headers, body, settings.RECALL_WORKSPACE_SECRET
    ):
        log.warning("Recall webhook rejected: invalid signature (%d bytes)", len(body))
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(body)
    except ValueError:
        log.warning("Recall webhook rejected: invalid JSON (%d bytes)", len(body))
        raise HTTPException(status_code=400, detail="Body is not valid JSON")
    if not isinstance(payload, dict):
        log.warning("Recall webhook rejected: JSON root is not an object")
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    event, bot_id, word_count = _webhook_metadata(payload)
    log.info(
        "Recall webhook received event=%s bot_id=%s words=%d",
        event or "<missing>",
        bot_id or "<missing>",
        word_count,
    )
    if settings.WEBHOOK_LOG_PAYLOADS:
        log.info("Recall webhook payload: %s", json.dumps(payload, ensure_ascii=False))
    outcome = handle_event(payload)
    log.info("Recall webhook processed event=%s outcome=%s", event or "<missing>", outcome)
    return {"ok": True, "outcome": outcome}
