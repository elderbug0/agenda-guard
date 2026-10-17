"""Drift engine: topic tracking with Easy / Medium / High rules, cooldown and alert escalation."""
from __future__ import annotations

from app.config import settings
from app.models import Session

# How many switches to a logically connected topic each mode allows (None = unlimited).
ALLOWED_SWITCHES = {"easy": None, "medium": 1, "high": 0}


def update(session: Session, result: dict, now: float) -> int | None:
    """Apply one analyzer result to the session.

    Returns the alert level (1 = first alert, 2 = every later alert) or None.
    May add "violation", "from_topic" and a new "reason" to `result` for the chat message.
    """
    relation = result.get("relation", "same")
    confidence = float(result.get("confidence", 0.0))
    on_home = bool(result.get("on_home_topic"))
    new_topic = (result.get("topic") or "").strip()

    # Right after a topic change the window still holds the old topic, so skip a few windows.
    if session.ignore_windows > 0:
        session.ignore_windows -= 1
        return None

    # Nothing to compare with yet (easy mode without a starting topic): adopt the first topic.
    if not session.topic:
        if new_topic:
            session.topic = new_topic
        return None

    # Coming back to the starting topic is always fine, in every mode.
    if on_home:
        session.topic = session.home_title() or session.topic
        session.switch_streak = 0
        return None

    # Still on the same topic (or the model is not sure): nothing happens.
    if relation == "same" or confidence < settings.CONFIDENCE_MIN:
        session.switch_streak = 0
        return None

    # The group is leaving the previous topic. Wait for a few windows in a row.
    session.switch_streak += 1
    if session.switch_streak < settings.STREAK_NEEDED:
        return None

    from_topic = session.topic
    violation = None
    if relation == "unrelated":
        violation = "jump"  # a sudden jump alerts in every mode
    else:  # "connected"
        session.switches += 1
        allowed = ALLOWED_SWITCHES.get(session.mode)
        if allowed is not None and session.switches > allowed:
            violation = "not_allowed" if session.mode == "high" else "too_many"

    # The new topic becomes the baseline either way, so one switch is flagged only once.
    session.topic = new_topic or session.topic
    session.switch_streak = 0
    session.ignore_windows = settings.MOVED_ON_IGNORE_WINDOWS
    matched = result.get("matched_item_id")
    if matched and session.item_by_id(matched) is not None:
        session.current_item_id = matched

    result["from_topic"] = from_topic
    if violation is None:
        result["status"] = "moved_on"
        result["reason"] = f"Moved to a connected topic: {session.topic}"
        return None

    result["violation"] = violation
    result["status"] = "off_track"
    result["category"] = "off_topic"
    result["reason"] = {
        "jump": f"Sudden jump from '{from_topic}' to '{session.topic}'",
        "not_allowed": f"Left the single topic for '{session.topic}'",
        "too_many": f"Another topic switch, to '{session.topic}'",
    }[violation]

    if now - session.last_alert_ts <= settings.COOLDOWN_S:
        return None
    session.alert_count += 1
    session.last_alert_ts = now
    return 1 if session.alert_count == 1 else 2