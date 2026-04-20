"""Auto-generate a UnitConfig by feeding teaching material into Claude.

The instructor pastes a lesson plan / textbook excerpt / notes, and this
module asks Claude Opus to produce:
  - subject
  - learning_goals
  - rubric_items (with keywords)
  - common_misconceptions
  - persona_initial_misconceptions (subset the AI will hold)

The output is merged into an in-memory UnitConfig the admin UI can show
in a preview + edit form before saving.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.config.settings import Settings, get_settings
from src.models.schemas import RubricItem, StudentAccount, UnitConfig
from src.services.claude_service import ClaudeServiceError

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM_PROMPT = """\
당신은 한국 과학교육 교재·교안을 분석해 Vygotsky 기반 AI 대화 시스템의
단원 설정(UnitConfig)을 자동 생성하는 조력자입니다.

아래 규칙을 지켜 분석하세요:
1. 교수자가 제공한 자료를 읽고, 이 단원의 핵심 학습 목표 3~6개를 추출한다.
2. 각 학습 목표를 학생이 말로 설명했을 때 달성했다고 판단할 루브릭 항목을 만든다.
   - item_id: 영어 소문자·밑줄 (예: 'condition_light', 'product_oxygen')
   - description: 한국어 한 줄 요약
   - keywords: 학생 설명에서 이 항목이 등장했다고 판단할 한국어 키워드 2~5개
   - required: 핵심 학습 목표면 true, 부가면 false
3. 이 단원에서 초·중등 학생들이 자주 가지는 오개념 3~6개를 한국어 완결 문장으로 쓴다.
4. 그 중 AI 페르소나(교대 동료 학습자)가 세션 시작 시 실제로 품고 시작할
   오개념 1~2개를 고른다. 너무 많으면 대화가 혼란스러워진다.
5. 과목(subject)은 '과학', '초등 과학 교과교육', '중학교 과학' 등 교수자 자료 톤에 맞춰 기입.
6. 출력은 반드시 아래 JSON 스키마만 따르며, 설명·주석·코드블록 백틱 없이 JSON 객체 하나만 반환.

출력 스키마:
{
  "subject": "string",
  "learning_goals": ["string", ...],
  "rubric_items": [
    {"item_id": "string", "description": "string", "keywords": ["string", ...], "required": true|false},
    ...
  ],
  "common_misconceptions": ["string", ...],
  "persona_initial_misconceptions": ["string", ...]
}
"""

_USER_TEMPLATE = """\
【단원명】
{unit_name}

【대상 학년】
{target_grade}

【교수자가 제공한 교안·교재·메모】
{content}

위 자료를 바탕으로 UnitConfig JSON 을 생성하세요."""


def _extract_json(text: str) -> dict[str, Any]:
    if not text:
        raise ValueError("empty response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError("Claude did not return JSON.")
    return json.loads(match.group(0))


def _claude_call(
    settings: Settings,
    user_prompt: str,
    *,
    client=None,
    max_tokens: int = 2500,
    temperature: float = 0.3,
) -> str:
    if client is None:
        if not settings.anthropic_api_key:
            raise ClaudeServiceError(
                "ANTHROPIC_API_KEY is not set. Enter one in the admin page first."
            )
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise ClaudeServiceError(
                "anthropic SDK not installed."
            ) from exc
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    import random as _random
    import time as _time

    kwargs = {
        "model": settings.claude_analysis_model,
        "max_tokens": max_tokens,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    use_temperature = True
    response = None
    last_exc: Exception | None = None
    _MAX_RETRY = 3

    for attempt in range(_MAX_RETRY + 1):
        call_kwargs = dict(kwargs)
        if use_temperature:
            call_kwargs["temperature"] = temperature
        try:
            response = client.messages.create(**call_kwargs)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            msg = str(exc).lower()
            if (
                "temperature" in msg and ("deprecated" in msg or "not" in msg)
                and use_temperature
            ):
                use_temperature = False
                continue
            if ("overload" in msg or "529" in msg) and attempt < _MAX_RETRY:
                _time.sleep(1.5 * (2 ** attempt) + _random.uniform(0, 0.4))
                continue
            logger.exception("auto-generate unit Claude call failed")
            raise ClaudeServiceError(f"Claude call failed: {exc}") from exc

    if response is None:
        raise ClaudeServiceError(
            f"Claude call failed after retries: {last_exc}"
        ) from last_exc

    chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "".join(chunks).strip()


def auto_generate_unit_from_text(
    *,
    unit_code: str,
    unit_name: str,
    target_grade: str,
    raw_content: str,
    persona_name: str = "지후",
    instructor_name: str = "교수",
    hint_max_count: int = 3,
    session_duration_minutes: int = 15,
    student_account_count: int = 30,
    settings: Settings | None = None,
    claude_client=None,
) -> UnitConfig:
    """Build a UnitConfig from a free-form teaching text using Claude.

    Raises ClaudeServiceError if the API is unreachable or the response
    can't be parsed. Caller (admin UI) can catch and surface the error.
    """

    settings = settings or get_settings()
    if not raw_content or not raw_content.strip():
        raise ValueError("교안·교재 내용을 입력해주세요.")
    if not unit_name.strip():
        raise ValueError("단원명이 필요합니다.")
    if not unit_code.strip():
        raise ValueError("단원 코드 (영어·하이픈) 가 필요합니다.")

    user_prompt = _USER_TEMPLATE.format(
        unit_name=unit_name.strip(),
        target_grade=(target_grade or "").strip() or "(미지정)",
        content=raw_content.strip(),
    )
    raw = _claude_call(settings, user_prompt, client=claude_client)

    try:
        parsed = _extract_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ClaudeServiceError(
            f"Claude 응답을 JSON 으로 해석하지 못했어요: {exc}\n\n원본:\n{raw[:500]}"
        ) from exc

    rubric_items: list[RubricItem] = []
    for i, item in enumerate(parsed.get("rubric_items") or []):
        if not isinstance(item, dict):
            continue
        try:
            rubric_items.append(
                RubricItem(
                    item_id=str(item.get("item_id") or f"r_{i+1}").strip(),
                    description=str(item.get("description") or "").strip(),
                    keywords=[
                        str(k).strip()
                        for k in (item.get("keywords") or [])
                        if str(k).strip()
                    ],
                    required=bool(item.get("required", True)),
                )
            )
        except Exception as exc:  # noqa: BLE001 - robust to malformed rubric items
            logger.warning("Skipping malformed rubric item %d: %s", i, exc)

    learning_goals = [
        str(g).strip() for g in (parsed.get("learning_goals") or []) if str(g).strip()
    ]
    common_misconceptions = [
        str(m).strip()
        for m in (parsed.get("common_misconceptions") or [])
        if str(m).strip()
    ]
    persona_initial_misconceptions = [
        str(m).strip()
        for m in (parsed.get("persona_initial_misconceptions") or [])
        if str(m).strip()
    ]
    # Ensure persona misconceptions are drawn from the common list (sanity check).
    for pm in list(persona_initial_misconceptions):
        if pm not in common_misconceptions and common_misconceptions:
            # If the picked initial misconception isn't in the common list,
            # don't invent one — drop it to keep internal consistency.
            persona_initial_misconceptions.remove(pm)
    if not persona_initial_misconceptions and common_misconceptions:
        persona_initial_misconceptions = common_misconceptions[:1]

    # Accounts are generated separately by the UI handler — we supply an empty
    # list here so UnitConfig validates.
    subject = str(parsed.get("subject") or "과학").strip()

    return UnitConfig(
        unit_code=unit_code.strip(),
        subject=subject,
        unit_name=unit_name.strip(),
        target_grade_for_teaching=(target_grade or "").strip() or None,
        learning_goals=learning_goals,
        rubric_items=rubric_items,
        common_misconceptions=common_misconceptions,
        persona_name=persona_name.strip() or "지후",
        persona_role="같은 단원을 공부하는 교대 동료 학생",
        persona_initial_misconceptions=persona_initial_misconceptions,
        hint_max_count=hint_max_count,
        session_duration_minutes=session_duration_minutes,
        instructor_name=instructor_name.strip() or "교수",
        student_accounts=[],
    )


def fill_student_accounts(unit: UnitConfig, count: int = 30) -> UnitConfig:
    """Populate a UnitConfig with N freshly-generated student accounts."""

    from src.tools.generate_codes import make_accounts

    accounts = make_accounts(count)
    unit.student_accounts = [
        StudentAccount(id=a["id"], password=a["password"]) for a in accounts
    ]
    return unit
