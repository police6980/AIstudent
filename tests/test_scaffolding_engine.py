"""Tests for the 4-layer prompt composition (preservice-teacher setup)."""

from __future__ import annotations

from src.models.enums import HintType
from src.models.schemas import RubricItem, StudentAccount, UnitConfig
from src.prompts import LAYER1_VYGOTSKY_PRINCIPLES, LAYER2_PRESERVICE
from src.services.scaffolding_engine import build_system_prompt, build_unit_layer


def _make_config(**overrides) -> UnitConfig:
    base = UnitConfig(
        unit_code="test-01",
        subject="초등 과학",
        unit_name="테스트 단원",
        target_grade_for_teaching="초등 5학년",
        learning_goals=["개념 A", "개념 B"],
        rubric_items=[
            RubricItem(item_id="r1", description="A를 설명", keywords=["A"], required=True),
            RubricItem(item_id="r2", description="B를 설명", keywords=["B"], required=False),
        ],
        common_misconceptions=["오개념 1", "오개념 2"],
        persona_name="지후",
        persona_initial_misconceptions=["오개념 1"],
        hint_max_count=3,
        hint_types_allowed=[HintType.SOCRATIC, HintType.METACOGNITIVE],
        session_duration_minutes=10,
        instructor_name="김교수",
        student_accounts=[StudentAccount(id="s01", password="abc12")],
    )
    return base.model_copy(update=overrides)


def test_prompt_contains_all_three_layers():
    cfg = _make_config()
    prompt = build_system_prompt(cfg)

    # Layer 1 markers
    assert "절대 원칙" in prompt
    assert "답을 먼저 주지 않는다" in prompt
    assert "오개념을 가진 학습자" in prompt  # role-reversal marker

    # Layer 2 markers
    assert "동료 학습자" in prompt
    assert "초등학생 흉내" in prompt  # explicit ban

    # Layer 3 markers (unit + persona + misconceptions + goals)
    assert "테스트 단원" in prompt
    assert "지후" in prompt
    assert "초등 5학년" in prompt  # target grade line
    assert "오개념 1" in prompt
    assert "개념 A" in prompt


def test_initial_misconceptions_explicit():
    cfg = _make_config(persona_initial_misconceptions=["오개념 2"])
    layer3 = build_unit_layer(cfg)
    # The explicitly-picked active misconception must appear under the "실제로 품고 있는" block.
    assert "실제로 품고 있는 오개념" in layer3
    assert "오개념 2" in layer3


def test_missing_initial_misconceptions_falls_back_to_common():
    cfg = _make_config(persona_initial_misconceptions=[])
    layer3 = build_unit_layer(cfg)
    assert "오개념 1" in layer3  # from common_misconceptions


def test_target_grade_optional():
    cfg = _make_config(target_grade_for_teaching=None)
    layer3 = build_unit_layer(cfg)
    assert "초등" not in layer3.split("【당신(AI)의 페르소나】")[0] or "단원:" in layer3
    # At minimum: no crash, unit_name still present
    assert "테스트 단원" in layer3


def test_textbook_content_truncated():
    cfg = _make_config(textbook_content="x" * 5000)
    layer3 = build_unit_layer(cfg)
    assert "(이하 생략)" in layer3


def test_layer1_invariants_preserved():
    # Guard against accidental mutation of the 6 principles text.
    for marker in [
        "답을 먼저 주지 않는다",
        "주도성을 지킵니다",
        "기여를 점차 줄입니다",
        "사고 방식을 매개합니다",
        "메타인지를 자극합니다",
        "정서적으로 안전한 공간",
    ]:
        assert marker in LAYER1_VYGOTSKY_PRINCIPLES, f"Missing principle marker: {marker}"


def test_layer2_preservice_mentions_role_reversal():
    assert "동료 학습자" in LAYER2_PRESERVICE
    assert "초등학생 흉내" in LAYER2_PRESERVICE  # explicit guardrail
