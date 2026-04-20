"""Orchestrates the preservice-teacher — AI peer dialogue lifecycle.

Phase A: text dialogue, resume-or-new logic, completion lock.
Phase B (future): analysis + PDF generation on completion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.config.unit_config import (
    UnitConfigError,
    authenticate,
    find_unit_config_by_code,
)
from src.db.database import init_db
from src.db.repository import SessionRepository
from src.models.enums import SessionStatus, Speaker
from src.models.schemas import Turn, UnitConfig
from src.services.claude_service import ClaudeService, ClaudeServiceError
from src.services.scaffolding_engine import build_system_prompt

logger = logging.getLogger(__name__)

DEFAULT_CONFIGS_DIR = Path("configs")
MAX_HISTORY_TURNS = 24  # Layer 4 window


class SessionLockedError(RuntimeError):
    """Raised when a student tries to access an already-completed session."""


class AuthenticationError(RuntimeError):
    """Raised when (unit_code, student_id, password) is invalid."""


@dataclass
class LoginResult:
    session_id: str
    unit_config: UnitConfig
    is_new: bool                  # True if we created a fresh session, False if resumed
    turns: list[Turn]             # existing turns (may be empty for new sessions)


class SessionManager:
    """High-level facade used by the UI."""

    def __init__(
        self,
        repo: Optional[SessionRepository] = None,
        claude: Optional[ClaudeService] = None,
        configs_dir: Path = DEFAULT_CONFIGS_DIR,
    ):
        init_db()
        self._repo = repo or SessionRepository()
        self._claude = claude or ClaudeService()
        self._configs_dir = configs_dir

    # -- auth & session resolution --------------------------------------

    def load_unit(self, unit_code: str) -> UnitConfig:
        """Resolve `unit_code` to a UnitConfig, surfacing a friendly error if missing."""

        try:
            return find_unit_config_by_code(unit_code, self._configs_dir)
        except UnitConfigError as exc:
            raise AuthenticationError(f"단원을 찾을 수 없어요: {exc}") from exc

    def login(self, unit_code: str, student_id: str, password: str) -> LoginResult:
        """Authenticate, then resume or create a session.

        Raises:
            AuthenticationError — unknown unit or bad credentials
            SessionLockedError — student already completed this unit's session
        """

        unit_config = self.load_unit(unit_code)
        if not authenticate(unit_config, student_id, password):
            raise AuthenticationError("학생 ID 또는 비밀번호가 올바르지 않아요.")

        existing = self._repo.find_session(unit_code, student_id)

        # Case 1: no session yet — create fresh + open with AI greeting.
        if existing is None:
            session_id = self._repo.create_session(unit_config, student_id)
            self._produce_opening_turn(session_id, unit_config)
            turns = self._repo.get_turns(session_id)
            return LoginResult(
                session_id=session_id, unit_config=unit_config, is_new=True, turns=turns
            )

        # Case 2: completed — locked.
        if existing.status == SessionStatus.COMPLETED:
            raise SessionLockedError(
                f"이미 완료된 세션이에요 ({existing.end_time:%Y-%m-%d %H:%M} 종료). "
                "다시 참여하려면 교수자에게 문의하세요."
            )

        # Case 3: in_progress — resume.
        turns = self._repo.get_turns(existing.session_id)
        return LoginResult(
            session_id=existing.session_id,
            unit_config=unit_config,
            is_new=False,
            turns=turns,
        )

    # -- conversation ---------------------------------------------------

    def _produce_opening_turn(self, session_id: str, unit_config: UnitConfig) -> Turn:
        system_prompt = build_system_prompt(unit_config)
        try:
            opening_text = self._claude.generate_response(system_prompt, history=[])
        except ClaudeServiceError as exc:
            logger.error("Failed to produce opening turn: %s", exc)
            opening_text = (
                f"(시스템 메시지: AI 응답 생성 실패 — {exc})\n"
                "환경변수 ANTHROPIC_API_KEY 가 설정되었는지 확인해주세요."
            )
        return self._repo.append_turn(session_id, Speaker.AI, opening_text)

    def submit_student_turn(self, session_id: str, student_text: str) -> Turn:
        """Persist the student utterance, generate the AI reply, return the AI turn."""

        student_text = (student_text or "").strip()
        if not student_text:
            raise ValueError("빈 입력은 보낼 수 없어요.")

        session_row = self._repo.get_session(session_id)
        if session_row is None:
            raise LookupError(f"세션을 찾을 수 없어요: {session_id}")
        if session_row.status == SessionStatus.COMPLETED.value:
            raise SessionLockedError("이미 종료된 세션이에요.")

        unit_config = UnitConfig.model_validate(session_row.unit_config_json)
        self._repo.append_turn(session_id, Speaker.STUDENT, student_text)

        history = self._repo.get_turns(session_id)
        if len(history) > MAX_HISTORY_TURNS:
            history = history[-MAX_HISTORY_TURNS:]

        system_prompt = build_system_prompt(unit_config)
        try:
            ai_text = self._claude.generate_response(system_prompt, history=history)
        except ClaudeServiceError as exc:
            logger.error("Claude reply failed: %s", exc)
            ai_text = f"(시스템 메시지: AI 응답 생성 실패 — {exc})"

        return self._repo.append_turn(session_id, Speaker.AI, ai_text)

    def complete_session(self, session_id: str) -> None:
        """Lock the session. Phase B will trigger analysis+PDF here."""

        self._repo.complete_session(session_id)
        logger.info("Session %s completed. Phase B analysis hook goes here.", session_id)

    # -- read-only ------------------------------------------------------

    def get_turns(self, session_id: str) -> list[Turn]:
        return self._repo.get_turns(session_id)
