"""Tests for the 4-layer prompt composition."""

from __future__ import annotations

import pytest

from src.models.enums import GradeLevel, HintType
from src.models.schemas import RubricItem, UnitConfig
from src.prompts import LAYER1_VYGOTSKY_PRINCIPLES
from src.prompts.layer2_grade import get_grade_layer_prompt
from src.services.scaffolding_engine import build_system_prompt, build_unit_layer


def _make_config(grade: GradeLevel) -> UnitConfig:
    return UnitConfig(
        session_code="test",
        grade_level=grade,
        subject="과학",
        unit_name="테스트 단원",
        learning_goals=["개념 A", "개념 B"],
        rubric_items=[
            RubricItem(item_id="r1", description="A를 언급", keywords=["A"], required=True),
            RubricItem(item_id="r2", description="B를 언급", keywords=["B"], required=False),
        ],
        common_misconceptions=["오개념 1"],
        persona_name="루나",
        persona_role="또래 친구",
        hint_max_count=3,
        hint_types_allowed=[HintType.BRIDGING, HintType.METACOGNITIVE],
        session_duration_minutes=10,
        teacher_email="t@e.kr",
        teacher_name="김교사",
    )


@pytest.mark.parametrize(
    "grade",
    [GradeLevel.ELEMENTARY, GradeLevel.MIDDLE, GradeLevel.HIGH, GradeLevel.SCIENCE_HIGH],
)
def test_prompt_builds_for_all_grades(grade: GradeLevel):
    cfg = _make_config(grade)
    prompt = build_system_prompt(cfg)

    # Layer 1 principle marker is present.
    assert "절대 원칙" in prompt
    assert "답을 주지 않습니다" in prompt
    # Layer 2 marker is present and matches the grade.
    layer2 = get_grade_layer_prompt(grade)
    assert layer2.split("\n", 1)[0] in prompt
    # Layer 3 unit context is present.
    assert "테스트 단원" in prompt
    assert "루나" in prompt
    assert "개념 A" in prompt


def test_layer1_invariant_text_reachable():
    # Guard: any accidental mutation of the principle text would break this.
    assert "사고 구조" not in LAYER1_VYGOTSKY_PRINCIPLES or "매개" in LAYER1_VYGOTSKY_PRINCIPLES
    assert "막힘" in LAYER1_VYGOTSKY_PRINCIPLES
    assert "기여를 점차 줄입니다" in LAYER1_VYGOTSKY_PRINCIPLES


def test_unit_layer_includes_persona_and_rubric():
    cfg = _make_config(GradeLevel.HIGH)
    layer3 = build_unit_layer(cfg)
    assert "루나" in layer3
    assert "또래 친구" in layer3
    assert "필수" in layer3  # rubric required marker
    assert "선택" in layer3  # rubric optional marker
    assert "오개념 1" in layer3


def test_textbook_content_truncated():
    cfg = _make_config(GradeLevel.HIGH).model_copy(update={"textbook_content": "x" * 5000})
    layer3 = build_unit_layer(cfg)
    assert "(이하 생략)" in layer3
