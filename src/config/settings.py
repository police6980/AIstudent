"""Runtime configuration loaded from .env / environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# Load .env once at import time. Safe no-op if the file is missing.
load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings snapshot."""

    anthropic_api_key: str | None
    claude_model: str
    openai_api_key: str | None
    elevenlabs_api_key: str | None
    elevenlabs_voice_id: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    smtp_from_address: str | None
    database_url: str
    report_dir: str
    log_level: str
    keep_audio_files: bool
    session_retention_days: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings object built from the environment."""

    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
        smtp_host=os.getenv("SMTP_HOST"),
        smtp_port=_env_int("SMTP_PORT", 587),
        smtp_user=os.getenv("SMTP_USER"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_from_address=os.getenv("SMTP_FROM_ADDRESS"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/sessions.db"),
        report_dir=os.getenv("REPORT_DIR", "data/reports"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        keep_audio_files=_env_bool("KEEP_AUDIO_FILES", False),
        session_retention_days=_env_int("SESSION_RETENTION_DAYS", 30),
    )
