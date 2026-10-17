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


class Event(BaseModel):
    ts: float
    status: str  # on_track | moved_on | off_track
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

    def prune(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        cutoff = now - settings.TRANSCRIPT_KEEP_S
        if self.transcript and self.transcript[0].ts < cutoff:
            self.transcript = [s for s in self.transcript if s.ts >= cutoff]

    def text_of_last(self, seconds: float, now: float | None = None) -> str:
        """Transcript text from the last `seconds`, without speaker names (topic only)."""
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
