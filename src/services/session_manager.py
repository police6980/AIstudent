"""Orchestrates the preservice-teacher — AI peer dialogue lifecycle.

State machine (Phase B2):
    PRE_MAP    — student builds initial concept map
    DIALOGUE   — map submitted, AI opens with diagnosis-informed question,
                 then back-and-forth
    POST_MAP   — student clicked 'end dialogue', now builds post-map
    REFLECTION — post-map submitted, student answers 5 reflection questions
    COMPLETED  — everything done, PDF available (Phase B5)

Rules:
    - Each transition must be explicit (submit_pre_concept_map, etc).
    - submit_student_turn is only valid in DIALOGUE.
    - Re-login resumes at the current_step.
    - COMPLETED sessions are locked (SessionLockedError).
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
from src.models.concept_map import ConceptMap
from src.models.enums import SessionStatus, SessionStep, Speaker
from src.models.schemas import Turn, UnitConfig
from src.services.analysis import run_full_analysis
from src.services.claude_service import ClaudeService, ClaudeServiceError
from src.services.concept_maps import (
    InitialDiagnosis,
    diagnose_initial_concept_map,
)
from src.services.diagnostics import load_reflection_questions
from src.services.pdf import ReportPaths, generate_reports_for_session
from src.services.scaffolding_engine import build_system_prompt

logger = logging.getLogger(__name__)

DEFAULT_CONFIGS_DIR = Path("configs")
MAX_HISTORY_TURNS = 16  # lowered from 24 — our system prompt is already ~4k tokens


class SessionLockedError(RuntimeError):
    """Raised when a student tries to access an already-completed session."""


class AuthenticationError(RuntimeError):
    """Raised when (unit_code, student_id, password) is invalid."""


class StepViolationError(RuntimeError):
    """Raised when a caller tries to perform an action out of step order."""


@dataclass
class LoginResult:
    session_id: str
    unit_config: UnitConfig
    is_new: bool
    current_step: SessionStep
    turns: list[Turn]


@dataclass
class PreMapResult:
    turns: list[Turn]
    diagnosis: Optional[InitialDiagnosis]
    next_step: SessionStep


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

    # -- auth & resume ---------------------------------------------------

    def load_unit(self, unit_code: str) -> UnitConfig:
        """Resolve `unit_code` to a UnitConfig with a friendly error on miss."""

        try:
            return find_unit_config_by_code(unit_code, self._configs_dir)
        except UnitConfigError as exc:
            raise AuthenticationError(f"단원을 찾을 수 없어요: {exc}") from exc

    def login(
        self,
        unit_code: str,
        student_id: str,
        password: str = "",
        student_name: str = "",
    ) -> LoginResult:
        """Authenticate, then resume or create a session at the appropriate step.

        Two login modes (chosen per-unit by the instructor):
          - "open":         student_id = 학번, password ignored, student_name required
          - "account_list": legacy — student_id + password must match a preset account
        """

        unit_config = self.load_unit(unit_code)

        mode = (getattr(unit_config, "student_login_mode", "open") or "open").strip()
        if mode == "open":
            student_id = (student_id or "").strip()
            student_name = (student_name or "").strip()
            if not student_id:
                raise AuthenticationError("학번을 입력해주세요.")
            if not student_name:
                raise AuthenticationError("이름을 입력해주세요.")
        else:
            if not authenticate(unit_config, student_id, password):
                raise AuthenticationError(
                    "학생 ID 또는 비밀번호가 올바르지 않아요."
                )

        existing = self._repo.find_session(unit_code, student_id)

        if existing is None:
            session_id = self._repo.create_session(
                unit_config, student_id, student_name=student_name or None
            )
            return LoginResult(
                session_id=session_id,
                unit_config=unit_config,
                is_new=True,
                current_step=SessionStep.PRE_MAP,
                turns=[],
            )

        if existing.status == SessionStatus.COMPLETED:
            raise SessionLockedError(
                f"이미 완료된 세션이에요 ({existing.end_time:%Y-%m-%d %H:%M} 종료). "
                "다시 참여하려면 교수자에게 문의하세요."
            )

        turns = self._repo.get_turns(existing.session_id)
        return LoginResult(
            session_id=existing.session_id,
            unit_config=unit_config,
            is_new=False,
            current_step=existing.current_step,
            turns=turns,
        )

    # -- step helpers ---------------------------------------------------

    def _get_session_or_raise(self, session_id: str):
        row = self._repo.get_session(session_id)
        if row is None:
            raise LookupError(f"세션을 찾을 수 없어요: {session_id}")
        if row.status == SessionStatus.COMPLETED.value:
            raise SessionLockedError("이미 종료된 세션이에요.")
        return row

    def _require_step(self, row, required: SessionStep) -> None:
        if row.current_step != required.value:
            raise StepViolationError(
                f"현재 단계는 '{row.current_step}' 인데 '{required.value}' 작업이 요청되었어요."
            )

    # -- PRE_MAP → DIALOGUE ----------------------------------------------

    def submit_pre_concept_map(
        self, session_id: str, concept_map: ConceptMap
    ) -> PreMapResult:
        """Persist the initial map, run diagnosis, transition to DIALOGUE.

        On Claude failure the map is still saved and the AI opens with a
        generic greeting; we do not block the student.
        """

        row = self._get_session_or_raise(session_id)
        self._require_step(row, SessionStep.PRE_MAP)

        self._repo.save_pre_concept_map(session_id, concept_map.model_dump(mode="json"))
        unit_config = UnitConfig.model_validate(row.unit_config_json)

        diagnosis: InitialDiagnosis | None = None
        try:
            diagnosis = diagnose_initial_concept_map(concept_map, unit_config)
            self._repo.save_initial_diagnosis(session_id, diagnosis.to_json())
        except ClaudeServiceError as exc:
            logger.error("Initial concept map diagnosis failed: %s", exc)
        except Exception as exc:  # noqa: BLE001 - any surprise shouldn't block student
            logger.exception("Unexpected failure in initial diagnosis: %s", exc)

        # Open the dialogue with an AI turn tailored to the diagnosis if available.
        opening_text = self._produce_opening_with_diagnosis(unit_config, diagnosis)
        self._repo.append_turn(session_id, Speaker.AI, opening_text)
        self._repo.update_step(session_id, SessionStep.DIALOGUE)

        return PreMapResult(
            turns=self._repo.get_turns(session_id),
            diagnosis=diagnosis,
            next_step=SessionStep.DIALOGUE,
        )

    def _produce_opening_with_diagnosis(
        self, unit_config: UnitConfig, diagnosis: InitialDiagnosis | None
    ) -> str:
        """Ask Claude to produce the opening AI turn, optionally guided by the diagnosis."""

        system_prompt = build_system_prompt(unit_config)
        if diagnosis and diagnosis.recommended_first_question:
            user_seed = (
                "(세션 시작) 학생이 방금 초기 개념도를 제출했어. "
                "진단 결과 학생은 다음 요소를 갖췄고(강점) 다음 지점에서 설명을 필요로 해:\n"
                f"- 강점: {', '.join(diagnosis.strong_points) or '(특이사항 없음)'}\n"
                f"- ZPD 목표: {', '.join(diagnosis.zpd_targets) or '(특이사항 없음)'}\n"
                "첫 발화는 페르소나로서 학생에게 가볍게 말을 걸어 아래 질문을 "
                "네 말로 자연스럽게 녹여서 던져줘. (질문을 그대로 복붙하지 말고 "
                "너의 말투로 각색해.)\n"
                f"추천 질문: \"{diagnosis.recommended_first_question}\""
            )
        else:
            user_seed = (
                "(세션 시작) 학생에게 페르소나로서 먼저 인사하며, "
                "방금 제출한 초기 개념도를 바탕으로 오늘 배운 내용을 네게 "
                "설명해달라고 자연스럽게 말을 걸어줘."
            )

        try:
            from src.models.schemas import Turn as TurnSchema  # local to avoid cycle
            seed_turn = TurnSchema.model_construct(
                turn_id="_seed",
                session_id="_seed",
                speaker=Speaker.STUDENT,
                content=user_seed,
                timestamp=__import__("datetime").datetime.utcnow(),
            )
            return self._claude.generate_response(system_prompt, history=[seed_turn])
        except ClaudeServiceError as exc:
            logger.error("Opening turn generation failed: %s", exc)
            return (
                "안녕, 오늘 단원 같이 정리해보기로 했지? "
                "네가 제출한 개념도 잘 봤어. 어디서부터 설명해줄래?"
            )

    # -- DIALOGUE --------------------------------------------------------

    def submit_student_turn(self, session_id: str, student_text: str) -> Turn:
        """Append the student's utterance and return the AI's reply."""

        student_text = (student_text or "").strip()
        if not student_text:
            raise ValueError("빈 입력은 보낼 수 없어요.")

        row = self._get_session_or_raise(session_id)
        self._require_step(row, SessionStep.DIALOGUE)

        unit_config = UnitConfig.model_validate(row.unit_config_json)
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

    def end_dialogue(self, session_id: str) -> None:
        """Transition DIALOGUE → POST_MAP. No PDF generation yet."""

        row = self._get_session_or_raise(session_id)
        self._require_step(row, SessionStep.DIALOGUE)
        self._repo.update_step(session_id, SessionStep.POST_MAP)

    # -- POST_MAP → REFLECTION -------------------------------------------

    def submit_post_concept_map(self, session_id: str, concept_map: ConceptMap) -> SessionStep:
        row = self._get_session_or_raise(session_id)
        self._require_step(row, SessionStep.POST_MAP)

        self._repo.save_post_concept_map(session_id, concept_map.model_dump(mode="json"))
        self._repo.update_step(session_id, SessionStep.REFLECTION)
        return SessionStep.REFLECTION

    # -- REFLECTION → COMPLETED ------------------------------------------

    def submit_reflection_answers(
        self,
        session_id: str,
        answers: dict[str, str],
    ) -> None:
        """Validate all reflection answers meet min_chars, then save + complete.

        Raises ValueError listing which questions fail the threshold. If any
        fail, nothing is saved — the UI re-prompts.
        """

        row = self._get_session_or_raise(session_id)
        self._require_step(row, SessionStep.REFLECTION)

        questions = load_reflection_questions()
        problems: list[str] = []
        normalized: dict[str, str] = {}
        for q in questions:
            text = (answers.get(q.id) or "").strip()
            ok, count = q.validate_answer(text)
            if not ok:
                problems.append(
                    f"'{q.title}' 응답이 {q.min_chars}자 이상 필요해요 (현재 {count}자)."
                )
            normalized[q.id] = text

        if problems:
            raise ValueError("\n".join(problems))

        self._repo.save_reflection_answers(session_id, normalized)
        # Mark completed first so the analysis orchestrator's completeness
        # check passes.
        self._repo.complete_session(session_id)
        # Run the full analysis pipeline. This is slow (~30-60s, several
        # Claude calls) but individual failures are swallowed into the
        # analysis bundle so the student still transitions to COMPLETED.
        try:
            run_full_analysis(session_id, repo=self._repo)
        except Exception as exc:  # noqa: BLE001 - never block completion
            logger.exception("run_full_analysis crashed: %s", exc)
        # Generate the PDF reports too. Also non-blocking.
        try:
            generate_reports_for_session(session_id, repo=self._repo)
        except Exception as exc:  # noqa: BLE001
            logger.exception("PDF generation crashed: %s", exc)

    def get_report_paths(self, session_id: str) -> ReportPaths | None:
        """Return the (summary, detail) PDF paths if they exist on disk."""

        from pathlib import Path

        from src.config.settings import get_settings

        row = self._repo.get_session(session_id)
        if row is None:
            return None
        settings = get_settings()
        candidates = list(
            Path(settings.report_dir).glob(
                f"{row.unit_code}_{row.student_id}_{session_id[:8]}"
            )
        )
        if not candidates:
            return None
        out_dir = candidates[0]
        summary = out_dir / "summary.pdf"
        detail = out_dir / "detail.pdf"
        if summary.exists() and detail.exists():
            return ReportPaths(summary=summary, detail=detail)
        return None

    # -- read-only helpers ----------------------------------------------

    def get_turns(self, session_id: str) -> list[Turn]:
        return self._repo.get_turns(session_id)
