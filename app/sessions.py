"""Session store. In-memory dict for now; swap the internals for Redis later."""
from __future__ import annotations

import uuid

from app.models import AgendaItem, Session


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._by_bot: dict[str, str] = {}

    def create(self, meeting_url: str, agenda: list[AgendaItem]) -> Session:
        session = Session(
            id=uuid.uuid4().hex[:12],
            meeting_url=meeting_url,
            agenda=agenda,
            current_item_id=agenda[0].id,
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_by_bot(self, bot_id: str) -> Session | None:
        session_id = self._by_bot.get(bot_id)
        return self._sessions.get(session_id) if session_id else None

    def attach_bot(self, session: Session, bot_id: str) -> None:
        session.bot_id = bot_id
        self._by_bot[bot_id] = session.id

    def all(self) -> list[Session]:
        return list(self._sessions.values())


store = SessionStore()
