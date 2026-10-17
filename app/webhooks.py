"""Recall.ai webhook handler: transcript events and bot status changes."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.loop import end_session
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
        text = words_to_text(inner.get("words") or [])
        if not text:
            return "ignored: empty transcript"
        speaker = (inner.get("participant") or {}).get("name") or "Unknown"
        if session.status == "waiting":
            session.status = "active"  # first words heard: the bot is in the call
        session.add_segment(speaker, text, now)
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


@router.post("/webhooks/recall")
async def recall_webhook(request: Request) -> dict:
    body = await request.body()
    if settings.RECALL_WORKSPACE_SECRET and not verify_signature(
        request.headers, body, settings.RECALL_WORKSPACE_SECRET
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Body is not valid JSON")
    outcome = handle_event(payload)
    log.debug("Webhook %s -> %s", payload.get("event"), outcome)
    return {"ok": True, "outcome": outcome}
