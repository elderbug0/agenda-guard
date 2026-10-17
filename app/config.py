"""Settings: environment variables (optionally loaded from a .env file) and thresholds."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader. Real environment variables always win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass
class Settings:
    # --- Recall.ai ---
    RECALL_API_KEY: str = ""
    RECALL_REGION: str = "us-east-1"  # must match the region of your Recall.ai account
    RECALL_WORKSPACE_SECRET: str = ""  # optional: verifies webhook signatures (whsec_...)
    TRANSCRIPT_LANGUAGE: str = "en"
    BOT_NAME: str = "Agenda Guard"

    # --- OpenAI ---
    OPENAI_API_KEY: str = ""
    ANALYZER_MODEL: str = "gpt-4o-mini"

    # --- Public URL Recall.ai calls back (your ngrok URL in development) ---
    WEBHOOK_BASE_URL: str = ""

    # --- Storage / assets ---
    DB_PATH: str = str(BASE_DIR / "agenda_guard.db")
    ALERT_SOUND_PATH: str = str(BASE_DIR / "app" / "sounds" / "alert.mp3")

    # --- Analysis loop ---
    # False = transcript-only mode: no OpenAI calls, no alerts, just the live transcript.
    ANALYSIS_ENABLED: bool = True
    ANALYSIS_INTERVAL_S: float = 20.0  # how often each active session is analyzed
    WINDOW_S: int = 90  # how much recent transcript the analyzer sees
    MIN_WORDS: int = 15  # skip a window with less speech than this
    TRANSCRIPT_KEEP_S: int = 600  # keep only the last ~10 minutes in memory

    # --- Drift engine ---
    STREAK_NEEDED: int = 3  # consecutive off-track windows before an alert
    CONFIDENCE_MIN: float = 0.7  # minimum confidence for an off-track window to count
    MOVED_ON_CONFIDENCE: float = 0.75  # confidence needed to switch the current item
    MOVED_ON_IGNORE_WINDOWS: int = 2  # windows to ignore after switching items
    COOLDOWN_S: int = 180  # minimum gap between alerts

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(BASE_DIR / ".env")
        d = cls()
        return cls(
            RECALL_API_KEY=_str("RECALL_API_KEY", d.RECALL_API_KEY),
            RECALL_REGION=_str("RECALL_REGION", d.RECALL_REGION),
            RECALL_WORKSPACE_SECRET=_str("RECALL_WORKSPACE_SECRET", d.RECALL_WORKSPACE_SECRET),
            TRANSCRIPT_LANGUAGE=_str("TRANSCRIPT_LANGUAGE", d.TRANSCRIPT_LANGUAGE),
            BOT_NAME=_str("BOT_NAME", d.BOT_NAME),
            OPENAI_API_KEY=_str("OPENAI_API_KEY", d.OPENAI_API_KEY),
            ANALYZER_MODEL=_str("ANALYZER_MODEL", d.ANALYZER_MODEL),
            WEBHOOK_BASE_URL=_str("WEBHOOK_BASE_URL", d.WEBHOOK_BASE_URL),
            DB_PATH=_str("DB_PATH", d.DB_PATH),
            ALERT_SOUND_PATH=_str("ALERT_SOUND_PATH", d.ALERT_SOUND_PATH),
            ANALYSIS_ENABLED=_bool("ANALYSIS_ENABLED", d.ANALYSIS_ENABLED),
            ANALYSIS_INTERVAL_S=_float("ANALYSIS_INTERVAL_S", d.ANALYSIS_INTERVAL_S),
            WINDOW_S=_int("WINDOW_S", d.WINDOW_S),
            MIN_WORDS=_int("MIN_WORDS", d.MIN_WORDS),
            TRANSCRIPT_KEEP_S=_int("TRANSCRIPT_KEEP_S", d.TRANSCRIPT_KEEP_S),
            STREAK_NEEDED=_int("STREAK_NEEDED", d.STREAK_NEEDED),
            CONFIDENCE_MIN=_float("CONFIDENCE_MIN", d.CONFIDENCE_MIN),
            MOVED_ON_CONFIDENCE=_float("MOVED_ON_CONFIDENCE", d.MOVED_ON_CONFIDENCE),
            MOVED_ON_IGNORE_WINDOWS=_int("MOVED_ON_IGNORE_WINDOWS", d.MOVED_ON_IGNORE_WINDOWS),
            COOLDOWN_S=_int("COOLDOWN_S", d.COOLDOWN_S),
        )


settings = Settings.from_env()
