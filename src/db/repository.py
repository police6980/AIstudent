"""CRUD operations for sessions, turns, and hint requests."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from src.db.database import get_session_factory
from src.models.db_models import HintRequestRow, SessionRow, TurnRow
from src.models.enums import HintType, Speaker
from src.models.schemas import HintRequest, Turn, UnitConfig


def _new_id() -> str:
    return uuid.uuid4().hex


class SessionRepository:
    """Thin repository over SessionRow / TurnRow / HintRequestRow."""

    def __init__(self, session_factory=None):
        self._factory = session_factory or get_session_factory()

    # -- sessions --------------------------------------------------------

    def create_session(self, student_name: str, unit_config: UnitConfig) -> str:
        """Create a new session row and return its id."""

        session_id = _new_id()
        with self._factory() as db:
            row = SessionRow(
                id=session_id,
                session_code=unit_config.session_code,
                student_name=student_name,
                grade_level=unit_config.grade_level.value,
                unit_name=unit_config.unit_name,
                persona_name=unit_config.persona_name,
                unit_config_json=unit_config.model_dump(mode="json"),
                start_time=datetime.utcnow(),
                hints_remaining=unit_config.hint_max_count,
            )
            db.add(row)
            db.commit()
        return session_id

    def end_session(self, session_id: str) -> None:
        """Stamp end_time on the given session."""

        with self._factory() as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise LookupError(f"Session not found: {session_id}")
            row.end_time = datetime.utcnow()
            db.commit()

    def get_session(self, session_id: str) -> Optional[SessionRow]:
        with self._factory() as db:
            return db.get(SessionRow, session_id)

    # -- turns -----------------------------------------------------------

    def append_turn(
        self,
        session_id: str,
        speaker: Speaker,
        content: str,
        *,
        audio_duration_sec: float | None = None,
        hint_type_used: HintType | None = None,
        annotations: dict | None = None,
    ) -> Turn:
        """Append a new turn and return it as a Pydantic Turn."""

        turn_id = _new_id()
        ts = datetime.utcnow()
        with self._factory() as db:
            # Determine next turn_index atomically within this transaction.
            existing = db.execute(
                select(TurnRow.turn_index)
                .where(TurnRow.session_id == session_id)
                .order_by(TurnRow.turn_index.desc())
                .limit(1)
            ).scalar_one_or_none()
            next_index = 0 if existing is None else existing + 1

            row = TurnRow(
                id=turn_id,
                session_id=session_id,
                turn_index=next_index,
                speaker=speaker.value,
                content=content,
                timestamp=ts,
                audio_duration_sec=audio_duration_sec,
                hint_type_used=hint_type_used.value if hint_type_used else None,
                annotations_json=annotations or {},
            )
            db.add(row)
            db.commit()

        return Turn(
            turn_id=turn_id,
            session_id=session_id,
            speaker=speaker,
            content=content,
            timestamp=ts,
            audio_duration_sec=audio_duration_sec,
            hint_type_used=hint_type_used,
            annotations=annotations or {},
        )

    def get_turns(self, session_id: str) -> list[Turn]:
        """Return all turns for a session ordered by turn_index."""

        with self._factory() as db:
            rows = (
                db.execute(
                    select(TurnRow)
                    .where(TurnRow.session_id == session_id)
                    .order_by(TurnRow.turn_index.asc())
                )
                .scalars()
                .all()
            )

        return [
            Turn(
                turn_id=r.id,
                session_id=r.session_id,
                speaker=Speaker(r.speaker),
                content=r.content,
                timestamp=r.timestamp,
                audio_duration_sec=r.audio_duration_sec,
                hint_type_used=HintType(r.hint_type_used) if r.hint_type_used else None,
                annotations=r.annotations_json or {},
            )
            for r in rows
        ]

    # -- hint requests ---------------------------------------------------

    def record_hint_request(self, session_id: str, requested_type: HintType) -> HintRequest:
        """Decrement hints_remaining and record a hint-request row."""

        ts = datetime.utcnow()
        with self._factory() as db:
            session_row = db.get(SessionRow, session_id)
            if session_row is None:
                raise LookupError(f"Session not found: {session_id}")
            before = session_row.hints_remaining
            if before <= 0:
                raise ValueError("No hints remaining.")
            session_row.hints_remaining = before - 1

            row = HintRequestRow(
                session_id=session_id,
                requested_type=requested_type.value,
                timestamp=ts,
                hints_remaining_before=before,
            )
            db.add(row)
            db.commit()

        return HintRequest(
            session_id=session_id,
            requested_type=requested_type,
            timestamp=ts,
            hints_remaining_before=before,
        )

    def get_hints_remaining(self, session_id: str) -> int:
        with self._factory() as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise LookupError(f"Session not found: {session_id}")
            return row.hints_remaining
