"""SQLAlchemy ORM tables for sessions, turns, and hint requests."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class SessionRow(Base):
    """One student-AI session."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_code: Mapped[str] = mapped_column(String(64), index=True)
    student_name: Mapped[str] = mapped_column(String(128))
    grade_level: Mapped[str] = mapped_column(String(32))
    unit_name: Mapped[str] = mapped_column(String(128))
    persona_name: Mapped[str] = mapped_column(String(64))
    unit_config_json: Mapped[dict] = mapped_column(JSON)
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hints_remaining: Mapped[int] = mapped_column(Integer, default=0)

    turns: Mapped[list[TurnRow]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="TurnRow.turn_index"
    )
    hint_requests: Mapped[list[HintRequestRow]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class TurnRow(Base):
    """A single utterance within a session."""

    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    audio_duration_sec: Mapped[float | None] = mapped_column(nullable=True)
    hint_type_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    annotations_json: Mapped[dict] = mapped_column(JSON, default=dict)

    session: Mapped[SessionRow] = relationship(back_populates="turns")


class HintRequestRow(Base):
    """Record of a single hint request (student pressed a hint button)."""

    __tablename__ = "hint_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    requested_type: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    hints_remaining_before: Mapped[int] = mapped_column(Integer)

    session: Mapped[SessionRow] = relationship(back_populates="hint_requests")
