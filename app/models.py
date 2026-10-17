"""Data models: AgendaItem, Segment, Event, Session (plus API request bodies)."""
from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings


class AgendaItem(BaseModel):
    id: str
    title: str
    description: str = ""
    minutes: int = 0


class Segment(BaseModel):
    speaker: str
    text: str
    ts: float  # wall-clock time (seconds) when the segment was received


class TranscriptWord(BaseModel):
    """One immutable word from Recall's timed transcript stream.

    ``start_timestamp`` and ``end_timestamp`` share Recall's media timeline.
    That timeline may be relative to the meeting, so it is intentionally kept
    separate from ``received_ts`` (the server's wall clock).
    """

    speaker: str
    text: str
    start_timestamp: float
    end_timestamp: float
    received_ts: float

    def fingerprint(self) -> str:
        """Stable idempotency key for Recall retries of the same word."""
        return "\x1f".join(
            (self.speaker, self.text, repr(self.start_timestamp), repr(self.end_timestamp))
        )


class Event(BaseModel):
    ts: float
    status: str  # on_track | moved_on | off_track
    category: Literal["on_topic", "off_topic"] = "on_topic"
    item_id: str | None = None
    confidence: float = 0.0
    reason: str = ""
    alert_level: int | None = None


class Session(BaseModel):
    id: str
    meeting_url: str
    bot_id: str | None = None
    agenda: list[AgendaItem]
    current_item_id: str
    transcript: list[Segment] = Field(default_factory=list)  # only the last ~10 min
    words: list[TranscriptWord] = Field(default_factory=list)  # ordered Recall media timeline
    word_fingerprints: set[str] = Field(default_factory=set, exclude=True)
    word_version: int = 0
    last_analyzed_word_version: int = 0
    pending_word_count: int = 0
    off_track_streak: int = 0
    alert_count: int = 0
    last_alert_ts: float = 0.0
    ignore_windows: int = 0  # windows to skip after a moved_on switch
    events: list[Event] = Field(default_factory=list)
    status: Literal["waiting", "active", "ended"] = "waiting"
    created_ts: float = Field(default_factory=time.time)
    ended_ts: float | None = None
    end_reason: str | None = None

    def item_by_id(self, item_id: str | None) -> AgendaItem | None:
        if item_id is None:
            return None
        return next((i for i in self.agenda if i.id == item_id), None)

    def current_item(self) -> AgendaItem:
        return self.item_by_id(self.current_item_id) or self.agenda[0]

    def add_segment(self, speaker: str, text: str, ts: float | None = None) -> None:
        ts = time.time() if ts is None else ts
        self.transcript.append(Segment(speaker=speaker, text=text, ts=ts))
        self.prune(ts)

    def add_words(self, speaker: str, words: list[TranscriptWord], received_ts: float | None = None) -> list[TranscriptWord]:
        """Add new words exactly once, keeping late webhook batches in timeline order."""
        received_ts = time.time() if received_ts is None else received_ts
        added: list[TranscriptWord] = []
        for word in words:
            fingerprint = word.fingerprint()
            if fingerprint in self.word_fingerprints:
                continue
            self.word_fingerprints.add(fingerprint)
            added.append(word)

        if added:
            self.words.extend(added)
            self.words.sort(key=lambda word: (word.end_timestamp, word.start_timestamp, word.received_ts))
            self.word_version += 1
            self.pending_word_count += len(added)
            self.prune(received_ts)
        return added

    def prune(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        cutoff = now - settings.TRANSCRIPT_KEEP_S
        if self.transcript and self.transcript[0].ts < cutoff:
            self.transcript = [s for s in self.transcript if s.ts >= cutoff]
        if self.words:
            # Recall timestamps are a coherent media clock, unlike webhook arrival times.
            word_cutoff = self.words[-1].end_timestamp - settings.TRANSCRIPT_KEEP_S
            self.words = [word for word in self.words if word.end_timestamp >= word_cutoff]
            self.word_fingerprints = {word.fingerprint() for word in self.words}

    def text_of_last(
        self, seconds: float, now: float | None = None, stable_delay_s: float = 0.0
    ) -> str:
        """Transcript text from the last `seconds`, without speaker names (topic only)."""
        if self.words:
            # Anchor the window to the newest media timestamp so delayed delivery
            # and relative meeting clocks cannot distort its contents.
            stable_until = self.words[-1].end_timestamp - stable_delay_s
            cutoff = stable_until - seconds
            return " ".join(
                word.text
                for word in self.words
                if cutoff <= word.end_timestamp <= stable_until
            )
        now = time.time() if now is None else now
        cutoff = now - seconds
        return "\n".join(s.text for s in self.transcript if s.ts >= cutoff)


# ---------- API request bodies ----------


class AgendaItemIn(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    minutes: int = Field(default=0, ge=0)
    id: str | None = None


class SessionCreate(BaseModel):
    meeting_url: str = Field(min_length=1)
    agenda: list[AgendaItemIn] = Field(min_length=1)
