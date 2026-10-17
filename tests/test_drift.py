"""Unit tests for the drift engine (no network, no fixtures)."""
from app import drift
from app.config import settings
from app.models import AgendaItem, Session


def make_session() -> Session:
    agenda = [
        AgendaItem(id="item-1", title="Roadmap"),
        AgendaItem(id="item-2", title="Hiring"),
    ]
    return Session(id="s1", meeting_url="https://meet.google.com/x", agenda=agenda, current_item_id="item-1")


def off(conf: float = 0.9) -> dict:
    return {"status": "off_track", "matched_item_id": None, "confidence": conf, "reason": "football"}


def on() -> dict:
    return {"status": "on_track", "matched_item_id": "item-1", "confidence": 0.9, "reason": "roadmap"}


def moved(item_id: str = "item-2", conf: float = 0.9) -> dict:
    return {"status": "moved_on", "matched_item_id": item_id, "confidence": conf, "reason": "hiring"}


def test_alert_after_three_consecutive_off_track_windows():
    s = make_session()
    assert drift.update(s, off(), 1000) is None
    assert drift.update(s, off(), 1020) is None
    assert drift.update(s, off(), 1040) == 1
    assert s.alert_count == 1
    assert s.off_track_streak == 0


def test_on_track_resets_streak():
    s = make_session()
    drift.update(s, off(), 1000)
    drift.update(s, off(), 1020)
    drift.update(s, on(), 1040)
    assert s.off_track_streak == 0
    assert drift.update(s, off(), 1060) is None


def test_low_confidence_does_not_count_and_resets_streak():
    s = make_session()
    drift.update(s, off(), 1000)
    drift.update(s, off(), 1020)
    assert drift.update(s, off(conf=settings.CONFIDENCE_MIN - 0.01), 1040) is None
    assert s.off_track_streak == 0


def test_confidence_exactly_at_minimum_counts():
    s = make_session()
    drift.update(s, off(conf=settings.CONFIDENCE_MIN), 1000)
    assert s.off_track_streak == 1


def test_cooldown_blocks_second_alert_then_escalates_to_level_two():
    s = make_session()
    for t in (1000, 1020):
        drift.update(s, off(), t)
    assert drift.update(s, off(), 1040) == 1

    # Another streak builds, but the cooldown has not passed yet.
    for t in (1060, 1080):
        assert drift.update(s, off(), t) is None
    assert drift.update(s, off(), 1100) is None  # streak reached, cooldown still active

    # Once the cooldown is over, the next off-track window fires level 2.
    assert drift.update(s, off(), 1040 + settings.COOLDOWN_S + 1) == 2
    assert s.alert_count == 2


def test_moved_on_switches_item_and_ignores_next_windows():
    s = make_session()
    drift.update(s, off(), 1000)
    assert drift.update(s, moved(), 1020) is None
    assert s.current_item_id == "item-2"
    assert s.off_track_streak == 0
    assert s.ignore_windows == settings.MOVED_ON_IGNORE_WINDOWS

    # The ignored windows must not build a streak, even if they look off-track.
    for t in range(settings.MOVED_ON_IGNORE_WINDOWS):
        assert drift.update(s, off(), 1040 + t * 20) is None
    assert s.off_track_streak == 0
    assert s.ignore_windows == 0


def test_moved_on_below_threshold_does_not_switch():
    s = make_session()
    assert drift.update(s, moved(conf=settings.MOVED_ON_CONFIDENCE), 1000) is None
    assert s.current_item_id == "item-1"


def test_moved_on_to_unknown_or_same_item_does_not_switch():
    s = make_session()
    drift.update(s, moved(item_id="item-99"), 1000)
    drift.update(s, moved(item_id="item-1"), 1020)
    assert s.current_item_id == "item-1"
    assert s.ignore_windows == 0
