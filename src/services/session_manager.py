"""Orchestrates the student-AI dialogue lifecycle (M1: text-only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.config.unit_config import UnitConfigError, find_unit_config_by_code
from src.db.database import init_db
from src.db.repository import SessionRepository
from src.models.enums import Speaker
from src.models.schemas import Turn, UnitConfig
from src.services.claude_service import ClaudeService, ClaudeServiceError
from src.services.scaffolding_engine import build_system_prompt

logger = logging.getLogger(__name__)

DEFAULT_CONFIGS_DIR = Path("configs")
MAX_HISTORY_TURNS = 20  # Layer 4 window


@dataclass
class StartSessionResult:
    session_id: str
    unit_config: UnitConfig
    opening_turn: Turn


class SessionManager:
    """High-level facade for UI code."""

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

    # -- lifecycle -------------------------------------------------------

    def start_session(self, session_code: str, student_name: str) -> StartSessionResult:
        """Resolve the unit config, create a session row, and produce the AI opening turn."""

        student_name = (student_name or "").strip() or "익명"
        try:
            unit_config = find_unit_config_by_code(session_code, self._configs_dir)
        except UnitConfigError as exc:
            raise ValueError(str(exc)) from exc

        session_id = self._repo.create_session(student_name, unit_config)
        system_prompt = build_system_prompt(unit_config)

        try:
            opening_text = self._claude.generate_response(system_prompt, history=[])
        except ClaudeServiceError as exc:
            # If Claude fails at start, still keep the session so the user sees the error.
            logger.error("Failed to produce opening turn: %s", exc)
            opening_text = (
                f"(시스템 메시지: AI 응답 생성 실패 — {exc})\n"
                "환경변수 ANTHROPIC_API_KEY 가 설정되었는지 확인해주세요."
            )

        opening_turn = self._repo.append_turn(session_id, Speaker.AI, opening_text)
        return StartSessionResult(
            session_id=session_id, unit_config=unit_config, opening_turn=opening_turn
        )

    def submit_student_turn(self, session_id: str, student_text: str) -> Turn:
        """Persist the student utterance, generate the AI reply, persist it, return the AI turn."""

        student_text = (student_text or "").strip()
        if not student_text:
            raise ValueError("Empty student input.")

        session_row = self._repo.get_session(session_id)
        if session_row is None:
            raise LookupError(f"Session not found: {session_id}")

        unit_config = UnitConfig.model_validate(session_row.unit_config_json)

        self._repo.append_turn(session_id, Speaker.STUDENT, student_text)

        history = self._repo.get_turns(session_id)
        # Clip to the most recent MAX_HISTORY_TURNS for Layer 4 window.
        if len(history) > MAX_HISTORY_TURNS:
            history = history[-MAX_HISTORY_TURNS:]

        system_prompt = build_system_prompt(unit_config)

        try:
            ai_text = self._claude.generate_response(system_prompt, history=history)
        except ClaudeServiceError as exc:
            logger.error("Claude reply failed: %s", exc)
            ai_text = f"(시스템 메시지: AI 응답 생성 실패 — {exc})"

        return self._repo.append_turn(session_id, Speaker.AI, ai_text)

    def end_session(self, session_id: str) -> None:
        """Stamp end_time on the session row. Report generation arrives in Milestone 4."""

        self._repo.end_session(session_id)

    # -- read-only helpers ----------------------------------------------

    def get_turns(self, session_id: str) -> list[Turn]:
        return self._repo.get_turns(session_id)
