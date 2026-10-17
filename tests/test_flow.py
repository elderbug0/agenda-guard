"""Flow tests: webhook handling, signature check, analysis tick, reactor. No network needed."""
import asyncio
import base64
import hashlib
import hmac
import os
import tempfile
import time
import uuid

from app import loop, reactor, webhooks
from app.config import settings
from app.models import AgendaItem, Session
from app.report import load_report
from app.sessions import store

LONG_TEXT = " ".join(["we should decide which feature to build first"] * 4)


def fresh_session() -> Session:
    """A new session with its own bot id, registered in the global store."""
    agenda = [AgendaItem(id="item-1", title="Roadmap"), AgendaItem(id="item-2", title="Hiring")]
    session = store.create("https://meet.google.com/x", agenda)
    store.attach_bot(session, f"bot-{uuid.uuid4().hex[:8]}")
    return session


def transcript_payload(bot_id: str, words: list[str], name: str = "Alex") -> dict:
    return {
        "event": "transcript.data",
        "data": {
            "data": {"words": [{"text": w} for w in words], "participant": {"id": 1, "name": name}},
            "bot": {"id": bot_id},
        },
    }


# ---------- webhooks ----------


def test_transcript_event_adds_segment_and_activates_session():
    s = fresh_session()
    assert s.status == "waiting"
    outcome = webhooks.handle_event(transcript_payload(s.bot_id, ["Hello", "team"]), now=1000.0)
    assert outcome == "segment added"
    assert s.status == "active"
    assert s.transcript[0].text == "Hello team"
    assert s.transcript[0].speaker == "Alex"


def test_unknown_bot_and_empty_transcript_are_ignored():
    s = fresh_session()
    assert webhooks.handle_event(transcript_payload("no-such-bot", ["hi"])).startswith("ignored")
    assert webhooks.handle_event(transcript_payload(s.bot_id, [])).startswith("ignored")
    assert s.transcript == []


def test_timed_words_are_ordered_and_retried_webhooks_are_deduplicated():
    s = fresh_session()
    payload = transcript_payload(s.bot_id, ["second", "first"])
    payload["data"]["data"]["words"] = [
        {"text": "second", "start_timestamp": 2.0, "end_timestamp": 2.4},
        {"text": "first", "start_timestamp": 1.0, "end_timestamp": 1.3},
    ]

    assert webhooks.handle_event(payload, now=1000.0) == "segment added"
    assert [(word.text, word.start_timestamp, word.end_timestamp) for word in s.words] == [
        ("first", 1.0, 1.3),
        ("second", 2.0, 2.4),
    ]
    assert s.text_of_last(0.49) == "second"
    assert webhooks.handle_event(payload, now=1001.0) == "ignored: duplicate transcript"
    assert len(s.words) == 2 and len(s.transcript) == 1


def test_status_events_activate_and_end_session_and_save_report():
    s = fresh_session()
    webhooks.handle_event({"event": "bot.in_call_recording", "data": {"bot": {"id": s.bot_id}}})
    assert s.status == "active"

    original_db = settings.DB_PATH
    settings.DB_PATH = os.path.join(tempfile.mkdtemp(), "test.db")
    try:
        webhooks.handle_event({"event": "bot.call_ended", "data": {"bot": {"id": s.bot_id}}})
        saved = load_report(s.id)
    finally:
        settings.DB_PATH = original_db

    assert s.status == "ended" and s.end_reason == "call_ended"
    assert saved is not None and saved["session_id"] == s.id
    # Late transcript events after the end are ignored.
    assert webhooks.handle_event(transcript_payload(s.bot_id, ["late"])).startswith("ignored")


def test_signature_verification():
    key = b"super-secret-key"
    secret = "whsec_" + base64.b64encode(key).decode()
    body = b'{"event":"transcript.data"}'
    msg_id, ts = "msg_1", str(int(time.time()))
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    headers = {"webhook-id": msg_id, "webhook-timestamp": ts, "webhook-signature": f"v1,{sig}"}
    assert webhooks.verify_signature(headers, body, secret)
    assert not webhooks.verify_signature(headers, b'{"event":"tampered"}', secret)
    assert not webhooks.verify_signature({**headers, "webhook-signature": "v1,AAAA"}, body, secret)
    assert not webhooks.verify_signature({}, body, secret)
    old = {**headers, "webhook-timestamp": str(int(time.time()) - 3600)}
    assert not webhooks.verify_signature(old, body, secret)


# ---------- analysis loop ----------


def test_two_off_track_ticks_fire_one_alert_and_log_events():
    s = fresh_session()
    original_analyze, original_react = loop.analyze, loop.react
    reacted: list[int] = []

    async def fake_analyze(session, text):
        return {"status": "off_track", "matched_item_id": None, "confidence": 0.9, "reason": "football"}

    async def fake_react(session, result, level):
        reacted.append(level)
        return {"chat": "ok", "sound": "ok"}

    loop.analyze, loop.react = fake_analyze, fake_react
    try:
        now = 10_000.0
        for i in range(2):
            s.add_segment("Alex", LONG_TEXT, now + i * 20)
            asyncio.run(loop.tick(s, now + i * 20 + 1))
    finally:
        loop.analyze, loop.react = original_analyze, original_react

    assert reacted == [1]
    assert [e.alert_level for e in s.events] == [None, 1]
    assert s.events[-1].reason == "football"
    assert s.events[-1].category == "off_topic"


def test_tick_skips_windows_with_too_little_speech():
    s = fresh_session()
    called: list[str] = []
    original = loop.analyze

    async def fake_analyze(session, text):
        called.append(text)
        return {"status": "on_track", "matched_item_id": None, "confidence": 1.0, "reason": ""}

    loop.analyze = fake_analyze
    try:
        s.add_segment("Alex", "hi there", 5000.0)
        assert asyncio.run(loop.tick(s, 5001.0)) is None
    finally:
        loop.analyze = original
    assert called == [] and s.events == []


# ---------- reactor ----------


def test_chat_text_is_short_and_name_free_template():
    s = fresh_session()
    result = {"reason": "A chat about last night's football game."}
    level1 = reactor.chat_text(s, result, 1)
    assert "Roadmap" in level1 and "football game" in level1 and "Alex" not in level1
    level2 = reactor.chat_text(s, result, 2)
    assert "Still off agenda" in level2 and "football" not in level2


def test_react_sends_both_and_one_failure_does_not_block_the_other():
    s = fresh_session()
    calls: list[str] = []

    class FakeRecall:
        async def send_chat(self, bot_id, message):
            calls.append("chat")
            raise RuntimeError("chat down")

        async def play_audio(self, bot_id, b64):
            calls.append("sound")

    original_recall, original_sound = reactor.recall, reactor.alert_mp3_b64
    reactor.recall, reactor.alert_mp3_b64 = FakeRecall(), lambda: "QUJD"
    try:
        outcome = asyncio.run(reactor.react(s, {"reason": "x"}, 1))
    finally:
        reactor.recall, reactor.alert_mp3_b64 = original_recall, original_sound

    assert sorted(calls) == ["chat", "sound"]
    assert outcome["sound"] == "ok" and outcome["chat"].startswith("error")
