"""Drift engine: off-track streak, confidence check, cooldown and alert escalation."""
from __future__ import annotations

from app.config import settings
from app.models import Session


def update(session: Session, result: dict, now: float) -> int | None:
    """Apply one analyzer result to the session.

    Returns the alert level (1 = first alert, 2 = every later alert) or None.
    """
    # Right after a topic switch the window still holds the old topic, so skip a few windows.
    if session.ignore_windows > 0:
        session.ignore_windows -= 1
        return None

    status = result.get("status")
    confidence = float(result.get("confidence", 0.0))
    matched = result.get("matched_item_id")

    if (
        status == "moved_on"
        and confidence > settings.MOVED_ON_CONFIDENCE
        and matched
        and matched != session.current_item_id
        and session.item_by_id(matched) is not None
    ):
        session.current_item_id = matched
        session.off_track_streak = 0
        session.ignore_windows = settings.MOVED_ON_IGNORE_WINDOWS
        return None

    if status == "off_track" and confidence >= settings.CONFIDENCE_MIN:
        session.off_track_streak += 1
    else:
        session.off_track_streak = 0

    if (
        session.off_track_streak >= settings.STREAK_NEEDED
        and now - session.last_alert_ts > settings.COOLDOWN_S
    ):
        session.alert_count += 1
        session.last_alert_ts = now
        session.off_track_streak = 0
        return 1 if session.alert_count == 1 else 2
    return None
