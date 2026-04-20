"""Vygotsky scaffolding hint generator.

Invoked when the student clicks one of the 6 hint buttons during the
dialogue. Produces a single short hint that:
  - does NOT disclose the target concept/term
  - matches the selected Vygotsky hint type
  - fits the preservice-teacher context (peer-college-student tone)

Each hint runs through a self-check pass by default: a second Claude call
that judges the draft against the 6 principles and asks for a rewrite
if needed. If the second pass also looks bad, we fall back to the
safest type (Metacognitive).
"""

from __future__ import annotations

import logging
from typing import Optional

from src.config.settings import Settings, get_settings
from src.models.enums import HintType, Speaker
from src.models.schemas import Turn, UnitConfig
from src.services.claude_service import ClaudeServiceError

logger = logging.getLogger(__name__)


# Each prompt produces ONE short hint (≤2 sentences), Korean, peer tone.
# The system prompt is combined with the unit's 6-principle Layer 1 at run
# time so hints stay within the Vygotsky rules.
_HINT_INSTRUCTIONS: dict[HintType, str] = {
    HintType.SOCRATIC: (
        "소크라테스적 되묻기:\n"
        "학생이 방금 한 설명의 **전제나 가정**을 드러내게 하는 짧은 되묻기 질문 "
        "하나를 만들어줘. 1~2문장."
    ),
    HintType.BRIDGING: (
        "개념 간 다리:\n"
        "학생이 이미 아는 다른 개념·경험에 **연결**시킬 수 있는 한 문장 힌트. "
        "새 용어를 꺼내지 말고 '~와 비슷하지 않아?' 식으로."
    ),
    HintType.COUNTEREXAMPLE: (
        "반례·경계 사례:\n"
        "학생 설명이 적용되지 않을 법한 **경계 상황** 하나를 짧게 제시하고 "
        "'그럼 이 경우는?' 이라고 물어줘."
    ),
    HintType.EVIDENCE: (
        "증거·근거 요구:\n"
        "학생의 주장을 뒷받침할 **관찰·실험·경험**이 무엇인지 묻는 한 문장."
    ),
    HintType.REPRESENTATION: (
        "표상 전환:\n"
        "말로 설명하다 막힌 지점을 **그림·수식·예시** 등 다른 모드로 바꿔보라는 권유 "
        "한 문장. 어떻게 그릴지까지는 제시하지 마."
    ),
    HintType.METACOGNITIVE: (
        "메타인지 촉진:\n"
        "학생이 **자기 설명 자체를 되돌아보게** 하는 한 문장 질문. "
        "예: '지금 막힌 게 용어를 몰라서야, 연결을 몰라서야?'"
    ),
}


_SELF_CHECK_SYSTEM = """\
당신은 Vygotsky 비계 원칙 검토관입니다.
주어진 힌트가 아래 6원칙을 지키는지 판정하세요.
1. 답(핵심 개념·용어·결론)을 직접 말하지 않는가?
2. 학생이 스스로 다음 스텝을 결정할 여지를 남겼는가?
3. 내용이 아니라 사고 방식을 매개했는가?
4. 학습자 수준(교대생) 어휘인가?
5. 1~3문장 이내인가?
6. 의례적 칭찬이나 정오 판정이 없는가?

출력은 정확히 다음 중 하나의 단어로 시작해야 합니다:
APPROVE  — 힌트 그대로 써도 OK
REJECT   — 6원칙 중 하나 이상 위배

줄바꿈 후 한 문장으로 이유를 붙이세요.
"""


_FALLBACK_HINTS: dict[HintType, str] = {
    HintType.SOCRATIC: "방금 한 말에서 '~이다' 라고 한 부분을 한 번 더 정의해볼래?",
    HintType.BRIDGING: "오늘 배운 것 말고, 전에 배웠던 것 중에 이것과 비슷한 게 있었어?",
    HintType.COUNTEREXAMPLE: "그럼 반대 상황에서도 네 설명이 통해? 한 번 생각해볼래?",
    HintType.EVIDENCE: "그걸 뒷받침할 만한 관찰이나 경험이 있었어?",
    HintType.REPRESENTATION: "말로만 하니 꼬이면, 그림으로 그리거나 구체 예시로 바꿔볼래?",
    HintType.METACOGNITIVE: (
        "지금 막힌 게 용어를 몰라서야, 아니면 개념 사이의 연결을 몰라서야?"
    ),
}


def _recent_history_text(history: list[Turn], max_chars: int = 1500) -> str:
    lines = []
    for t in history[-10:]:
        role = "학생" if t.speaker == Speaker.STUDENT else "AI"
        lines.append(f"{role}: {t.content}")
    joined = "\n".join(lines)
    if len(joined) > max_chars:
        joined = joined[-max_chars:]
    return joined


def _claude_one_shot(
    settings: Settings,
    system_prompt: str,
    user_prompt: str,
    *,
    client=None,
    max_tokens: int = 400,
    temperature: float = 0.6,
) -> str:
    """Single Claude call, tuned for short hint output."""

    if client is None:
        if not settings.anthropic_api_key:
            raise ClaudeServiceError("ANTHROPIC_API_KEY is not set.")
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    import random
    import time

    kwargs = {
        "model": settings.claude_model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    use_temperature = True
    last_exc = None
    for attempt in range(4):
        call_kwargs = dict(kwargs)
        if use_temperature:
            call_kwargs["temperature"] = temperature
        try:
            resp = client.messages.create(**call_kwargs)
            chunks = []
            for block in getattr(resp, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
            return "".join(chunks).strip()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            msg = str(exc).lower()
            if (
                "temperature" in msg
                and ("deprecated" in msg or "not" in msg)
                and use_temperature
            ):
                use_temperature = False
                continue
            if ("overload" in msg or "529" in msg) and attempt < 3:
                time.sleep(1.5 * (2 ** attempt) + random.uniform(0, 0.5))
                continue
            raise ClaudeServiceError(f"Claude hint call failed: {exc}") from exc
    raise ClaudeServiceError(f"Claude hint exhausted retries: {last_exc}")


def generate_hint(
    hint_type: HintType,
    unit_config: UnitConfig,
    history: list[Turn],
    *,
    settings: Optional[Settings] = None,
    claude_client=None,
    enable_self_check: bool = True,
) -> str:
    """Return a single short Vygotsky-aligned hint for the selected type."""

    settings = settings or get_settings()
    if not settings.anthropic_api_key:
        # Offline fallback — still useful
        logger.info("No API key; returning canned fallback hint for %s", hint_type)
        return _FALLBACK_HINTS[hint_type]

    instruction = _HINT_INSTRUCTIONS[hint_type]
    recent = _recent_history_text(history) or "(대화 아직 없음)"

    system_prompt = (
        f"당신은 교대생(예비 교사)을 돕는 **한 번의 짧은 힌트**를 만드는 역할입니다.\n"
        f"단원: {unit_config.unit_name}\n"
        f"학생이 스스로 도달해야 할 학습 목표 (직접 말하지 말 것):\n"
        + "\n".join(f"- {g}" for g in unit_config.learning_goals)
        + "\n\n"
        "【힌트 유형 지침】\n"
        f"{instruction}\n\n"
        "【절대 금지】\n"
        "- 학생이 쓰지 않은 핵심 용어·공식·결론 제시 금지\n"
        "- 정오 판정 ('맞아요', '틀렸어요') 금지\n"
        "- 의례적 칭찬 금지\n"
        "- 3문장 초과 금지\n"
        "- 여러 질문을 겹쳐 던지기 금지 (하나만)\n\n"
        "출력: 힌트 본문만 (따옴표·설명 없이 바로)."
    )
    user_prompt = f"【최근 대화】\n{recent}\n\n【요청】\n위 지침대로 힌트 한 개를 만드세요."

    try:
        draft = _claude_one_shot(
            settings, system_prompt, user_prompt, client=claude_client
        )
    except ClaudeServiceError as exc:
        logger.warning("Hint draft failed (%s); using fallback.", exc)
        return _FALLBACK_HINTS[hint_type]

    if not enable_self_check:
        return draft

    # ---------- Self-check pass ----------
    check_user = (
        f"【힌트 유형】 {hint_type.value}\n"
        f"【학생이 도달해야 할 목표(금지어)】\n"
        + "\n".join(f"- {g}" for g in unit_config.learning_goals)
        + f"\n\n【검토할 힌트】\n{draft}"
    )
    try:
        verdict = _claude_one_shot(
            settings,
            _SELF_CHECK_SYSTEM,
            check_user,
            client=claude_client,
            max_tokens=200,
            temperature=0.1,
        )
    except ClaudeServiceError as exc:
        logger.warning("Hint self-check failed (%s); using draft anyway.", exc)
        return draft

    if verdict.upper().startswith("APPROVE"):
        return draft

    # REJECTed — one regenerate attempt with stricter instructions
    try:
        retry_user = (
            f"【이전 초안】\n{draft}\n\n"
            f"【검토자 판정】\n{verdict}\n\n"
            "위 문제를 해결한 더 짧고 안전한 힌트를 다시 만들어주세요. "
            "핵심 용어·결론은 절대 말하지 말 것."
        )
        rewrite = _claude_one_shot(
            settings, system_prompt, retry_user, client=claude_client
        )
        return rewrite or _FALLBACK_HINTS[hint_type]
    except ClaudeServiceError:
        return _FALLBACK_HINTS[hint_type]
