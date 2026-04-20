"""Pydantic schemas for configs, accounts, turns, hints, and reports."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import HintType, SessionStatus, SessionStep, Speaker


class RubricItem(BaseModel):
    """One learning-goal rubric item defined by the instructor."""

    item_id: str
    description: str
    keywords: list[str] = Field(default_factory=list)
    required: bool = True


class StudentAccount(BaseModel):
    """A single student's login credentials for a unit."""

    id: str
    password: str


class UnitConfig(BaseModel):
    """Instructor-authored configuration for a single unit.

    A unit corresponds to a URL (?unit=<unit_code>) that the instructor shares
    with students. Each unit has its own student accounts.
    """

    unit_code: str                                # URL slug, e.g. "photo-01"
    subject: str                                  # e.g. "과학" or "초등 과학 교육론"
    unit_name: str                                # e.g. "광합성"
    target_grade_for_teaching: Optional[str] = None  # e.g. "초등 6학년" — the grade the preservice teacher expects to teach
    learning_goals: list[str]
    rubric_items: list[RubricItem]
    common_misconceptions: list[str] = Field(default_factory=list)
    persona_name: str                             # AI peer-learner's name
    persona_role: str = "이해가 부족하고 오개념을 가진 동료 학습자"
    persona_initial_misconceptions: list[str] = Field(default_factory=list)
    # subset of common_misconceptions the AI actively holds at session start
    hint_max_count: int = 3
    hint_types_allowed: list[HintType] = Field(default_factory=list)
    session_duration_minutes: int = 15
    # Teaching material the AI can reference during the dialogue (RAG-lite).
    # Also used by the auto-generator to extract goals/rubric/misconceptions.
    textbook_content: Optional[str] = None
    instructor_name: str
    # Login mode:
    #   "open"         — any student enters their 학번 + 이름; no preset accounts
    #   "account_list" — legacy: preset id/password pairs in student_accounts
    student_login_mode: str = "open"
    student_accounts: list[StudentAccount] = Field(default_factory=list)
    # When True, the AI is allowed to use Anthropic's server-side web_search
    # tool during student dialogue — helpful for fetching concrete examples
    # or analogies beyond the pasted textbook_content. Off by default to keep
    # the default cost/latency footprint low.
    web_search_enabled: bool = False


class Turn(BaseModel):
    """A single dialogue turn (student or AI)."""

    turn_id: str
    session_id: str
    speaker: Speaker
    content: str
    timestamp: datetime
    audio_duration_sec: Optional[float] = None
    hint_type_used: Optional[HintType] = None
    annotations: dict = Field(default_factory=dict)


class HintRequest(BaseModel):
    """Record of one hint button press."""

    session_id: str
    requested_type: HintType
    timestamp: datetime
    hints_remaining_before: int


class SessionInfo(BaseModel):
    """Summary of a session row (Phase A surface)."""

    session_id: str
    unit_code: str
    student_id: str
    persona_name: str
    start_time: datetime
    end_time: Optional[datetime]
    status: SessionStatus
    current_step: SessionStep = SessionStep.PRE_MAP


class SessionReport(BaseModel):
    """Teacher-facing report produced at session end (Phase B)."""

    session_id: str
    student_id: str
    unit_config: UnitConfig
    start_time: datetime
    end_time: datetime
    total_turns: int
    rubric_achievement: dict[str, bool] = Field(default_factory=dict)
    misconceptions_detected: list[str] = Field(default_factory=list)
    hints_used: list[HintRequest] = Field(default_factory=list)
    notable_moments: list[str] = Field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = Field(default_factory=list)


__all__ = [
    "RubricItem",
    "StudentAccount",
    "UnitConfig",
    "Turn",
    "HintRequest",
    "SessionInfo",
    "SessionReport",
]
