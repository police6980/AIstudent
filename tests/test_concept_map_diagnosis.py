"""Tests for the initial concept-map diagnosis pipeline (Claude mocked)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.config.settings import get_settings
from src.models.concept_map import Concept, ConceptMap, Proposition
from src.models.schemas import RubricItem, UnitConfig
from src.services.concept_maps.diagnosis import (
    InitialDiagnosis,
    diagnose_initial_concept_map,
)


class _StubClaudeContent:
    def __init__(self, text: str):
        self.text = text


class _StubClaudeResponse:
    def __init__(self, text: str):
        self.content = [_StubClaudeContent(text)]


class _StubClaudeMessages:
    def __init__(self, reply: str, capture: dict[str, Any]):
        self._reply = reply
        self._capture = capture

    def create(self, **kwargs):
        self._capture.update(kwargs)
        return _StubClaudeResponse(self._reply)


class StubClaudeClient:
    def __init__(self, reply: str):
        self.captured: dict[str, Any] = {}
        self.messages = _StubClaudeMessages(reply, self.captured)


def _unit_config() -> UnitConfig:
    return UnitConfig(
        unit_code="photo",
        subject="과학",
        unit_name="광합성",
        learning_goals=["광합성의 조건", "광합성의 산물"],
        rubric_items=[RubricItem(item_id="r1", description="빛 언급", keywords=["빛"])],
        common_misconceptions=["식물은 흙에서 양분을 흡수해 자란다"],
        persona_name="지후",
        persona_initial_misconceptions=["식물은 흙에서 양분을 흡수해 자란다"],
        instructor_name="김교수",
    )


def _sample_map() -> ConceptMap:
    return ConceptMap(
        concepts=[
            Concept(id="c1", label="광합성"),
            Concept(id="c2", label="빛"),
            Concept(id="c3", label="흙"),
        ],
        propositions=[
            Proposition(from_id="c1", to_id="c2", linking_phrase="의 조건은"),
            Proposition(from_id="c1", to_id="c3", linking_phrase="에서 양분을 얻음"),
        ],
    )


def test_diagnose_happy_path(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()

    reply = json.dumps(
        {
            "level": "developing",
            "level_justification": "개념 수는 적당하나 오개념 1개 검출됨.",
            "detected_misconceptions": [
                {"misconception": "식물은 흙에서 양분을 흡수", "evidence_in_map": "c1-c3 명제"}
            ],
            "missing_core_concepts": ["엽록체", "이산화탄소"],
            "strong_points": ["빛을 조건으로 인식"],
            "zpd_targets": ["양분의 출처 재개념화"],
            "recommended_first_question": "흙이 식물에게 해주는 역할이 뭘까?",
        },
        ensure_ascii=False,
    )
    client = StubClaudeClient(reply)

    diag = diagnose_initial_concept_map(_sample_map(), _unit_config(), claude_client=client)

    assert isinstance(diag, InitialDiagnosis)
    assert diag.level == "developing"
    assert len(diag.detected_misconceptions) == 1
    assert "엽록체" in diag.missing_core_concepts
    assert diag.recommended_first_question.startswith("흙")
    assert diag.novak_score is not None
    # Score should include the misconception penalty (1 misconception)
    # propositions=2, levels=2 → 2 + 10 - 5 = 7
    assert diag.novak_score.total == 7.0

    # Claude was called with the analysis model
    assert client.captured["model"]
    assert "광합성" in client.captured["system"] or "광합성" in str(client.captured.get("messages"))


def test_diagnose_handles_non_json_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    client = StubClaudeClient("죄송합니다. 분석할 수 없습니다.")  # no JSON
    diag = diagnose_initial_concept_map(_sample_map(), _unit_config(), claude_client=client)
    assert diag.level == "unknown"
    assert "JSON 파싱 실패" in diag.level_justification
    # Still returns a score based on rule layer
    assert diag.novak_score is not None


def test_diagnose_json_embedded_in_prose(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    prose_wrapped = (
        "다음은 분석 결과입니다:\n\n"
        + json.dumps(
            {
                "level": "proficient",
                "level_justification": "ok",
                "detected_misconceptions": [],
                "missing_core_concepts": [],
                "strong_points": ["a"],
                "zpd_targets": [],
                "recommended_first_question": "q",
            },
            ensure_ascii=False,
        )
        + "\n\n이상입니다."
    )
    client = StubClaudeClient(prose_wrapped)
    diag = diagnose_initial_concept_map(_sample_map(), _unit_config(), claude_client=client)
    assert diag.level == "proficient"
    assert diag.strong_points == ["a"]


def test_to_json_serialisable():
    client = StubClaudeClient(
        json.dumps(
            {
                "level": "novice",
                "level_justification": "...",
                "detected_misconceptions": [],
                "missing_core_concepts": [],
                "strong_points": [],
                "zpd_targets": [],
                "recommended_first_question": "?",
            },
            ensure_ascii=False,
        )
    )
    import os

    os.environ["ANTHROPIC_API_KEY"] = "fake"
    get_settings.cache_clear()
    diag = diagnose_initial_concept_map(_sample_map(), _unit_config(), claude_client=client)
    payload = diag.to_json()
    # Must be JSON-serialisable
    json.dumps(payload, ensure_ascii=False)
    assert payload["level"] == "novice"
    assert "novak_score" in payload
    assert "hierarchy" in payload


def test_diagnose_requires_api_key_without_client(monkeypatch):
    # No injected client AND no API key → should raise
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(Exception):
        diagnose_initial_concept_map(_sample_map(), _unit_config())
