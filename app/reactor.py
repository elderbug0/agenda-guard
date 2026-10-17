"""Reactor: sends the Meet chat message and plays the alert sound at the same time."""
from __future__ import annotations

import asyncio
import base64
import logging
from functools import lru_cache
from pathlib import Path

from app.config import settings
from app.models import Session
from app.recall_client import recall

log = logging.getLogger("agenda_guard.reactor")


def _clean_reason(reason: str, limit: int = 140) -> str:
    text = " ".join(reason.split()).rstrip(".")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def chat_text(session: Session, result: dict, level: int) -> str:
    """Short, neutral and name-free: the whole call sees this message."""
    home = session.home_item()
    target = home.title if home else (result.get("from_topic") or session.current_item().title)
    kind = result.get("violation")
    old = _clean_reason(result.get("from_topic", ""))
    new = _clean_reason(result.get("topic", ""))
    if level >= 2:
        return f"🚨 Still off track. Let's get back to: {target}."
    if kind == "jump":
        change = f"from '{old}' to '{new}'" if old else f"to '{new}'"
        return f"⚠️ Sudden topic change {change}. Let's get back to: {target}."
    if kind == "not_allowed":
        return f"⚠️ This meeting is set to one topic: {target}. The talk moved to '{new}'."
    if kind == "too_many":
        return f"⚠️ That's another topic switch, and only one is allowed. Back to: {target}."
    # Test alert or anything without a violation kind.
    message = f"⚠️ Off agenda? We're on: {session.current_item().title}."
    reason = _clean_reason(result.get("reason", ""))
    return f"{message} (Sounds like: {reason})" if reason else message


@lru_cache(maxsize=1)
def alert_mp3_b64() -> str:
    """The alert clip as base64, or "" if the file is missing or empty (chat still works)."""
    path = Path(settings.ALERT_SOUND_PATH)
    if not path.is_file() or path.stat().st_size == 0:
        log.warning("Alert sound %s is missing or empty; alerts will be chat-only", path)
        return ""
    return base64.b64encode(path.read_bytes()).decode()


async def react(session: Session, result: dict, level: int) -> dict[str, str]:
    """Send the chat message and play the sound in parallel.

    One channel failing never blocks the other. Returns an outcome per channel.
    """
    if not session.bot_id:
        return {"chat": "skipped: no bot", "sound": "skipped: no bot"}

    names = ["chat"]
    jobs = [recall.send_chat(session.bot_id, chat_text(session, result, level))]
    sound = alert_mp3_b64()
    outcome: dict[str, str] = {}
    if sound:
        names.append("sound")
        jobs.append(recall.play_audio(session.bot_id, sound))
    else:
        outcome["sound"] = "skipped: no alert.mp3"

    results = await asyncio.gather(*jobs, return_exceptions=True)
    for name, res in zip(names, results):
        if isinstance(res, BaseException):
            log.warning("Alert %s failed: %s", name, res)
            outcome[name] = f"error: {res}"
        else:
            outcome[name] = "ok"
    return outcome