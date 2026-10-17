"""Keyword alarm: when a configured word is heard, post a chat message and play the sound."""
from __future__ import annotations

import asyncio
import logging
import os
import re

from app.config import settings  # noqa: F401  (importing it loads the .env file first)
from app.reactor import alert_mp3_b64
from app.recall_client import recall

log = logging.getLogger("agenda_guard.keywords")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


# Comma-separated list in .env, e.g. ALERT_KEYWORDS=police,fire
KEYWORDS: list[str] = [
    " ".join(_words(k)) for k in os.environ.get("ALERT_KEYWORDS", "police").split(",") if _words(k)
]
try:
    COOLDOWN_S = float(os.environ.get("ALERT_KEYWORD_COOLDOWN_S", "15"))
except ValueError:
    COOLDOWN_S = 15.0

_last_alert: dict[str, float] = {}
_background: set[asyncio.Task] = set()


def find_keyword(text: str) -> str | None:
    """Return the first keyword found as a whole word (or phrase) in the text."""
    joined = " " + " ".join(_words(text)) + " "
    for keyword in KEYWORDS:
        if f" {keyword} " in joined:
            return keyword
    return None


async def _alert(bot_id: str, keyword: str) -> None:
    jobs = {"chat": recall.send_chat(bot_id, f'🚨 Keyword alert: "{keyword}" was mentioned.')}
    sound = alert_mp3_b64()
    if sound:
        jobs["sound"] = recall.play_audio(bot_id, sound)
    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    for name, res in zip(jobs, results):
        if isinstance(res, BaseException):
            log.warning("Keyword alert %s failed: %s", name, res)
        else:
            log.info("Keyword alert %s ok", name)


def check_keywords(session, text: str, now: float) -> None:
    """Called for every new piece of transcript. Fires the alert in the background."""
    if not session.bot_id:
        return
    keyword = find_keyword(text)
    if keyword is None:
        return
    if now - _last_alert.get(session.id, 0.0) < COOLDOWN_S:
        return
    _last_alert[session.id] = now
    log.info("Keyword %r heard in session %s", keyword, session.id)
    try:
        task = asyncio.get_running_loop().create_task(_alert(session.bot_id, keyword))
    except RuntimeError:  # no running event loop (for example in a plain sync test)
        return
    _background.add(task)
    task.add_done_callback(_background.discard)