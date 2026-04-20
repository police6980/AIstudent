"""Compose the 4-layer system prompt for Claude.

Layer 1: Vygotsky 6 principles (invariant)
Layer 2: Grade-level variation
Layer 3: Unit / persona / rubric / misconception context
Layer 4: Runtime dialogue state (injected by caller via message history)
"""

from __future__ import annotations

from src.models.schemas import UnitConfig
from src.prompts import LAYER1_VYGOTSKY_PRINCIPLES, get_grade_layer_prompt


def _format_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (없음)"


def _format_rubric(unit_config: UnitConfig) -> str:
    if not unit_config.rubric_items:
        return "- (없음)"
    lines = []
    for item in unit_config.rubric_items:
        mark = "필수" if item.required else "선택"
        lines.append(f"- [{mark}] {item.description}")
    return "\n".join(lines)


def build_unit_layer(unit_config: UnitConfig) -> str:
    """Layer 3 — per-session unit context."""

    textbook_block = ""
    if unit_config.textbook_content:
        # Trim long textbook text to keep the system prompt manageable.
        # Full RAG integration will come later.
        snippet = unit_config.textbook_content.strip()
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "\n...(이하 생략)"
        textbook_block = f"\n\n【참고 교과서 발췌】\n{snippet}\n"

    return f"""\
【단원 맥락 — 이번 세션】
과목: {unit_config.subject}
단원: {unit_config.unit_name}

【당신의 페르소나】
이름: {unit_config.persona_name}
역할: {unit_config.persona_role}
당신은 이 이름으로 학생에게 말을 걸고, 학생의 설명을 듣는 또래/동료 역할을 맡습니다.

【학생이 도달해야 할 학습 목표 — 직접 말하지 말 것】
{_format_bullets(unit_config.learning_goals)}

【평가 루브릭 — 학생이 스스로 도달해야 하는 지점】
{_format_rubric(unit_config)}

【알려진 오개념 — 발견하면 즉시 교정하지 말고, 학생이 스스로 되돌아보게 유도】
{_format_bullets(unit_config.common_misconceptions)}

【교과서 자료 사용 규칙】
교과서 내용을 참조할 수 있더라도, 학생에게 그대로 읊지 않습니다.
학생이 스스로 찾거나 떠올리도록 질문만 던집니다.{textbook_block}

【세션 운영】
예상 대화 시간: 약 {unit_config.session_duration_minutes}분.
대화 시작 시, 페르소나로서 학생에게 자연스럽게 말을 걸어 오늘 배운 내용을
당신에게 설명해달라고 부탁하세요. (단원명을 자연스럽게 언급해도 됩니다.)
"""


def build_system_prompt(unit_config: UnitConfig) -> str:
    """Assemble the final system prompt for this session.

    Returns a single string combining layers 1, 2, 3 in order. Layer 4 (live
    dialogue state) is conveyed via the Claude message history, not this prompt.
    """

    parts = [
        LAYER1_VYGOTSKY_PRINCIPLES.strip(),
        get_grade_layer_prompt(unit_config.grade_level).strip(),
        build_unit_layer(unit_config).strip(),
    ]
    return "\n\n---\n\n".join(parts)
