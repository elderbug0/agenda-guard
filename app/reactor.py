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
    item = session.current_item().title
    if level == 1:
        message = f"⚠️ Off agenda? We're on: {item}."
        reason = _clean_reason(result.get("reason", ""))
        return f"{message} (Sounds like: {reason})" if reason else message
    return f"🚨 Still off agenda. Current item: {item}. Time to get back on track."


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
