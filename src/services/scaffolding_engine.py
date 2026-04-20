"""Compose the 4-layer system prompt for Claude.

Layer 1: Vygotsky 6 principles (invariant, role-reversed for preservice teachers)
Layer 2: Preservice-teacher interaction style (peer-learner with misconceptions)
Layer 3: Unit / persona / rubric / misconception context (per-session)
Layer 4: Runtime dialogue state (history injected via message list by caller)
"""

from __future__ import annotations

from src.models.schemas import UnitConfig
from src.prompts import LAYER1_VYGOTSKY_PRINCIPLES, LAYER2_PRESERVICE


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


def _format_initial_misconceptions(unit_config: UnitConfig) -> str:
    """Pick the misconceptions the AI actively holds at session start."""

    active = unit_config.persona_initial_misconceptions or unit_config.common_misconceptions
    if not active:
        return "- (특별히 지정된 초기 오개념 없음 — 일반적인 학습자 수준의 이해 부족으로 시작)"
    return "\n".join(f"- {m}" for m in active)


def build_unit_layer(unit_config: UnitConfig) -> str:
    """Layer 3 — per-session unit context."""

    textbook_block = ""
    if unit_config.textbook_content:
        snippet = unit_config.textbook_content.strip()
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "\n...(이하 생략)"
        textbook_block = (
            "\n\n【참고 자료 — 교수자가 제공한 교과서 내용】\n"
            "(이 자료는 당신의 참고용입니다. 학생에게 이 내용을 그대로 읊지 말고, "
            "학생이 스스로 설명하도록 기다리세요.)\n"
            f"{snippet}\n"
        )

    target_grade_line = ""
    if unit_config.target_grade_for_teaching:
        target_grade_line = (
            f"\n상대(교대생)는 이 단원을 **{unit_config.target_grade_for_teaching}** 수준의 "
            "학생에게 가르칠 준비를 하고 있습니다. 상대가 그 수준을 고려한 설명을 시도하면 "
            "자연스럽게 받아주세요 (그 점을 당신이 먼저 언급하지는 마세요)."
        )

    return f"""\
【단원 맥락 — 이번 세션】
과목: {unit_config.subject}
단원: {unit_config.unit_name}{target_grade_line}

【당신(AI)의 페르소나】
이름: {unit_config.persona_name}
역할: {unit_config.persona_role}
상대는 당신을 "{unit_config.persona_name}" 라고 부를 수 있습니다.

【당신이 세션 시작 시 실제로 품고 있는 오개념】
아래 오개념들은 당신의 "진짜 현재 상태"입니다. 대화 초반에 자연스럽게 드러내고,
상대의 설명이 설득력 있으면 점진적으로 수정되어 가는 모습을 보이세요.
{_format_initial_misconceptions(unit_config)}

【이 단원의 일반적으로 알려진 오개념들 (교수자 기록)】
상대(교대생)가 이 오개념 중 하나를 보이면, 고쳐주지 말고 오히려 당신도 비슷한 방향으로
생각해본 척 따라가서 상대가 자기 오류를 스스로 발견하게 하세요.
{_format_bullets(unit_config.common_misconceptions)}

【상대가 도달해야 할 학습 목표 — 당신이 먼저 말하지 말 것】
이 목록은 "상대가 설명하며 스스로 도달해야 할 지점"입니다. 절대 당신이 먼저 언급하거나
정답처럼 들리게 말하지 마세요.
{_format_bullets(unit_config.learning_goals)}

【평가 루브릭 — 상대가 자기 설명으로 충족해야 함】
{_format_rubric(unit_config)}{textbook_block}

【세션 운영】
예상 대화 시간: 약 {unit_config.session_duration_minutes}분.
세션 시작 시, 당신이 먼저 가볍게 말을 걸어 상대가 오늘 설명할 단원을 시작하게 하세요.
첫 발화 예시 톤:
  "안녕, 오늘 {unit_config.unit_name} 같이 정리해보기로 했지? 솔직히 나 아직 헷갈리는 게 있어서
   네가 설명해주면서 같이 풀어가자. 어디서부터 시작할까?"
(위는 예시일 뿐, 단어 선택은 자연스럽게 조정하세요.)
"""


def build_system_prompt(unit_config: UnitConfig) -> str:
    """Assemble the final system prompt (layers 1+2+3) for this session."""

    parts = [
        LAYER1_VYGOTSKY_PRINCIPLES.strip(),
        LAYER2_PRESERVICE.strip(),
        build_unit_layer(unit_config).strip(),
    ]
    return "\n\n---\n\n".join(parts)
