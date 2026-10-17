"""End-of-meeting report built from the session events, saved in SQLite."""
from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone

from app.config import settings
from app.models import Session


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def build_report(session: Session) -> dict:
    end = session.ended_ts or time.time()
    counts = Counter(e.status for e in session.events)
    total = len(session.events)

    def title(item_id: str | None) -> str | None:
        item = session.item_by_id(item_id)
        return item.title if item else None

    events = [
        {
            "time": _iso(e.ts),
            "status": e.status,
            "item_id": e.item_id,
            "item_title": title(e.item_id),
            "confidence": e.confidence,
            "reason": e.reason,
            "alert_level": e.alert_level,
        }
        for e in session.events
    ]
    return {
        "session_id": session.id,
        "meeting_url": session.meeting_url,
        "status": session.status,
        "end_reason": session.end_reason,
        "started_at": _iso(session.created_ts),
        "ended_at": _iso(session.ended_ts),
        "duration_s": round(end - session.created_ts),
        "agenda": [i.model_dump() for i in session.agenda],
        "final_item_id": session.current_item_id,
        "windows_analyzed": total,
        "status_counts": dict(counts),
        "off_track_share": round(counts.get("off_track", 0) / total, 3) if total else 0.0,
        "alert_count": session.alert_count,
        "alerts": [e for e in events if e["alert_level"]],  # each alert keeps the reason it fired
        "events": events,
    }


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(settings.DB_PATH)


def init_db() -> None:
    with closing(_connect()) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS reports ("
            "session_id TEXT PRIMARY KEY, created_at REAL NOT NULL, body TEXT NOT NULL)"
        )
        db.commit()


def save_report(report: dict) -> None:
    init_db()
    with closing(_connect()) as db:
        db.execute(
            "INSERT OR REPLACE INTO reports (session_id, created_at, body) VALUES (?, ?, ?)",
            (report["session_id"], time.time(), json.dumps(report)),
        )
        db.commit()


def load_report(session_id: str) -> dict | None:
    init_db()
    with closing(_connect()) as db:
        row = db.execute("SELECT body FROM reports WHERE session_id = ?", (session_id,)).fetchone()
    return json.loads(row[0]) if row else None
