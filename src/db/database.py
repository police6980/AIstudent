"""SQLAlchemy engine and session factory."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import get_settings
from src.models.db_models import Base


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create parent directory for sqlite file URLs if missing."""

    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        db_path = Path(database_url[len(prefix) :])
        db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a process-wide SQLAlchemy engine."""

    settings = get_settings()
    _ensure_sqlite_dir(settings.database_url)
    engine = create_engine(
        settings.database_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False}
        if settings.database_url.startswith("sqlite")
        else {},
    )
    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return a cached sessionmaker bound to the engine."""

    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they don't exist."""

    Base.metadata.create_all(bind=get_engine())
