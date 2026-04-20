"""CRUD operations for sessions, turns, and hint requests."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from src.db.database import get_session_factory
from src.models.db_models import HintRequestRow, SessionRow, TurnRow
from src.models.enums import HintType, SessionStatus, SessionStep, Speaker
from src.models.schemas import HintRequest, SessionInfo, Turn, UnitConfig


def _new_id() -> str:
    return uuid.uuid4().hex


class SessionRepository:
    """Thin repository over SessionRow / TurnRow / HintRequestRow."""

    def __init__(self, session_factory=None):
        self._factory = session_factory or get_session_factory()

    # -- sessions --------------------------------------------------------

    def create_session(
        self,
        unit_config: UnitConfig,
        student_id: str,
        student_name: str | None = None,
    ) -> str:
        """Create a new in_progress session for (unit_code, student_id)."""

        session_id = _new_id()
        with self._factory() as db:
            row = SessionRow(
                id=session_id,
                unit_code=unit_config.unit_code,
                student_id=student_id,
                student_name=(student_name or "").strip() or None,
                unit_name=unit_config.unit_name,
                persona_name=unit_config.persona_name,
                unit_config_json=unit_config.model_dump(mode="json"),
                start_time=datetime.utcnow(),
                status=SessionStatus.IN_PROGRESS.value,
                current_step=SessionStep.PRE_MAP.value,
                hints_remaining=unit_config.hint_max_count,
            )
            db.add(row)
            db.commit()
        return session_id

    def complete_session(self, session_id: str) -> None:
        """Mark the session as completed and stamp end_time."""

        with self._factory() as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise LookupError(f"Session not found: {session_id}")
            row.end_time = datetime.utcnow()
            row.status = SessionStatus.COMPLETED.value
            row.current_step = SessionStep.COMPLETED.value
            db.commit()

    def update_step(self, session_id: str, step: SessionStep) -> None:
        """Advance the session's current_step marker."""

        with self._factory() as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise LookupError(f"Session not found: {session_id}")
            row.current_step = step.value
            db.commit()

    def get_session(self, session_id: str) -> Optional[SessionRow]:
        with self._factory() as db:
            return db.get(SessionRow, session_id)

    def find_session(self, unit_code: str, student_id: str) -> Optional[SessionInfo]:
        """Return the most recent session for (unit_code, student_id), if any."""

        with self._factory() as db:
            row = (
                db.execute(
                    select(SessionRow)
                    .where(
                        SessionRow.unit_code == unit_code,
                        SessionRow.student_id == student_id,
                    )
                    .order_by(SessionRow.start_time.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return SessionInfo(
                session_id=row.id,
                unit_code=row.unit_code,
                student_id=row.student_id,
                persona_name=row.persona_name,
                start_time=row.start_time,
                end_time=row.end_time,
                status=SessionStatus(row.status),
                current_step=SessionStep(row.current_step or SessionStep.PRE_MAP.value),
            )

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
        """Append a new turn, atomically computing turn_index."""

        turn_id = _new_id()
        ts = datetime.utcnow()
        with self._factory() as db:
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

    # -- analysis (Phase B hook) ----------------------------------------

    def save_analysis(self, session_id: str, analysis: dict) -> None:
        """Persist the Phase B analysis JSON onto the session row."""

        with self._factory() as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise LookupError(f"Session not found: {session_id}")
            row.analysis_json = analysis
            db.commit()

    # -- concept maps / diagnosis / reflection (Phase B) ----------------

    def save_pre_concept_map(self, session_id: str, payload: dict) -> None:
        self._save_json_column(session_id, "pre_concept_map_json", payload)

    def save_post_concept_map(self, session_id: str, payload: dict) -> None:
        self._save_json_column(session_id, "post_concept_map_json", payload)

    def save_initial_diagnosis(self, session_id: str, payload: dict) -> None:
        self._save_json_column(session_id, "initial_diagnosis_json", payload)

    def save_reflection_answers(self, session_id: str, payload: dict) -> None:
        self._save_json_column(session_id, "reflection_answers_json", payload)

    def _save_json_column(self, session_id: str, column: str, value: dict) -> None:
        with self._factory() as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                raise LookupError(f"Session not found: {session_id}")
            setattr(row, column, value)
            db.commit()
