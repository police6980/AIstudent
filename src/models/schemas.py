"""Pydantic schemas for configs, turns, hints, and reports."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from src.models.enums import GradeLevel, HintType, Speaker


class RubricItem(BaseModel):
    """One learning-goal rubric item defined by the teacher."""

    item_id: str
    description: str
    keywords: list[str] = Field(default_factory=list)
    required: bool = True


class UnitConfig(BaseModel):
    """Teacher-authored configuration for a single session/unit."""

    session_code: str
    grade_level: GradeLevel
    subject: str
    unit_name: str
    learning_goals: list[str]
    rubric_items: list[RubricItem]
    common_misconceptions: list[str] = Field(default_factory=list)
    persona_name: str
    persona_role: str
    hint_max_count: int = 3
    hint_types_allowed: list[HintType] = Field(default_factory=list)
    session_duration_minutes: int = 15
    textbook_content: Optional[str] = None
    teacher_email: str  # kept as str (not EmailStr) to avoid email-validator dep in MVP
    teacher_name: str


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


class SessionReport(BaseModel):
    """Teacher-facing report produced at session end (Milestone 4)."""

    session_id: str
    student_name: str
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


# Re-export EmailStr so tests/other modules can import from one place if needed.
__all__ = [
    "EmailStr",
    "RubricItem",
    "UnitConfig",
    "Turn",
    "HintRequest",
    "SessionReport",
]
