"""Tests for the Vygotsky hint generator (Claude mocked)."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.config.settings import get_settings
from src.models.enums import HintType, Speaker
from src.models.schemas import RubricItem, Turn, UnitConfig
from src.services.hint_generator import (
    _FALLBACK_HINTS,
    _HINT_INSTRUCTIONS,
    generate_hint,
)


class _Content:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Content(text)]


class _Messages:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = 0

    def create(self, **_):
        text = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return _Response(text)


class StubClaudeClient:
    def __init__(self, replies):
        self.messages = _Messages(replies)


def _unit():
    return UnitConfig(
        unit_code="u",
        subject="과학",
        unit_name="광합성",
        learning_goals=["광합성의 조건"],
        rubric_items=[RubricItem(item_id="r1", description="빛", keywords=["빛"])],
        persona_name="지후",
        instructor_name="교수",
    )


def _history():
    return [
        Turn(
            turn_id="t1",
            session_id="s",
            speaker=Speaker.AI,
            content="광합성 얘기할까?",
            timestamp=datetime.utcnow(),
        ),
        Turn(
            turn_id="t2",
            session_id="s",
            speaker=Speaker.STUDENT,
            content="광합성은 식물이 빛으로 에너지를 만드는 과정이야.",
            timestamp=datetime.utcnow(),
        ),
    ]


def test_all_hint_types_have_instructions_and_fallbacks():
    for ht in HintType:
        assert ht in _HINT_INSTRUCTIONS, f"missing instruction for {ht}"
        assert ht in _FALLBACK_HINTS, f"missing fallback for {ht}"
        assert _FALLBACK_HINTS[ht], "fallback hint empty"


def test_hint_approved_first_try(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    client = StubClaudeClient(
        ["방금 '만든다'는 게 정확히 어떤 뜻이야?", "APPROVE\n이유: 6원칙 지킴."]
    )
    out = generate_hint(HintType.SOCRATIC, _unit(), _history(), claude_client=client)
    assert "만든다" in out
    # 2 calls: draft + self-check
    assert client.messages.calls == 2


def test_hint_rejected_then_rewritten(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    client = StubClaudeClient(
        [
            "정답은 엽록체입니다.",  # draft disclosing answer
            "REJECT\n이유: 핵심 개념 직접 유출.",  # self-check
            "그럼 식물 안에서 어디서 그 일이 일어날까?",  # rewrite
        ]
    )
    out = generate_hint(
        HintType.METACOGNITIVE, _unit(), _history(), claude_client=client
    )
    assert "엽록체" not in out
    assert client.messages.calls == 3


def test_hint_falls_back_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    # No client passed; should hit the offline fallback path.
    out = generate_hint(HintType.BRIDGING, _unit(), _history())
    assert out == _FALLBACK_HINTS[HintType.BRIDGING]


def test_hint_disable_self_check(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    client = StubClaudeClient(["단 하나의 초안입니다."])
    out = generate_hint(
        HintType.EVIDENCE,
        _unit(),
        _history(),
        claude_client=client,
        enable_self_check=False,
    )
    assert out == "단 하나의 초안입니다."
    assert client.messages.calls == 1


def test_hint_all_types_runnable(monkeypatch):
    """Smoke: every HintType completes with APPROVE stub."""

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    for ht in HintType:
        client = StubClaudeClient([f"힌트-{ht.value}", "APPROVE\n이유: ok"])
        out = generate_hint(ht, _unit(), _history(), claude_client=client)
        assert out.startswith("힌트-") or out == _FALLBACK_HINTS[ht]
