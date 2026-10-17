"""Recall.ai client: create bot, send chat message, play audio, remove bot.

Endpoints and payloads follow the Recall.ai docs checked on 2026-10-17:
- POST /bot/                          create a bot (real-time transcript webhook + audio output)
- POST /bot/{id}/send_chat_message/   Google Meet supports to="everyone" only, max 500 characters
- POST /bot/{id}/output_audio/        mp3 only; the bot must be created with automatic_audio_output
- POST /bot/{id}/leave_call/          remove the bot from the meeting
Recall.ai changes things from time to time, so re-check the docs if a call starts failing.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

from app.config import settings

log = logging.getLogger("agenda_guard.recall")

CHAT_MAX_CHARS = 500  # Google Meet limit


class RecallError(RuntimeError):
    pass


def silent_mp3_b64() -> str:
    """A tiny silent MP3 (10 frames of MPEG-1 Layer III, 128 kbps, 44.1 kHz).

    Recall.ai requires `automatic_audio_output` when the bot is created, so we give it silence.
    """
    frame = bytes([0xFF, 0xFB, 0x90, 0x00]) + bytes(413)  # 417 bytes per frame
    return base64.b64encode(frame * 10).decode()


class RecallClient:
    def __init__(self) -> None:
        self._http: Any = None

    @property
    def base_url(self) -> str:
        return f"https://{settings.RECALL_REGION}.recall.ai/api/v1"

    def _client(self):
        if self._http is None:
            import httpx  # imported lazily so the app can start without it configured

            self._http = httpx.AsyncClient(timeout=30)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _post(self, path: str, payload: dict | None = None) -> dict:
        resp = await self._client().post(
            f"{self.base_url}{path}",
            headers={"Authorization": settings.RECALL_API_KEY, "accept": "application/json"},
            json=payload or {},
        )
        if resp.status_code >= 400:
            raise RecallError(f"POST {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    async def create_bot(self, meeting_url: str, webhook_url: str) -> str:
        body = {
            "meeting_url": meeting_url,
            "bot_name": settings.BOT_NAME,
            "recording_config": {
                "transcript": {
                    "provider": {
                        "recallai_streaming": {
                            "mode": "prioritize_low_latency",
                            "language_code": settings.TRANSCRIPT_LANGUAGE,
                        }
                    }
                },
                "realtime_endpoints": [
                    {"type": "webhook", "url": webhook_url,
                     "events": ["transcript.data", "transcript.partial_data"]}
                ],
            },
            "automatic_audio_output": {
                "in_call_recording": {"data": {"kind": "mp3", "b64_data": silent_mp3_b64()}}
            },
        }
        data = await self._post("/bot/", body)
        return data["id"]

    async def send_chat(self, bot_id: str, message: str) -> None:
        await self._post(
            f"/bot/{bot_id}/send_chat_message/",
            {"to": "everyone", "message": message[:CHAT_MAX_CHARS]},
        )

    async def play_audio(self, bot_id: str, b64_mp3: str) -> None:
        await self._post(f"/bot/{bot_id}/output_audio/", {"kind": "mp3", "b64_data": b64_mp3})

    async def remove_bot(self, bot_id: str) -> None:
        await self._post(f"/bot/{bot_id}/leave_call/")


recall = RecallClient()
