"""Tests for the B4 analysis pipeline (rule-based + LLM orchestration)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.config.settings import get_settings
from src.db.database import Base, get_engine, get_session_factory
from src.db.repository import SessionRepository
from src.models.concept_map import Concept, ConceptMap, Proposition
from src.models.enums import Speaker
from src.models.schemas import RubricItem, Turn, UnitConfig
from src.services.analysis.orchestrator import run_full_analysis
from src.services.analysis.rule_based import (
    HESITATION_PATTERNS,
    METACOGNITIVE_PATTERNS,
    analyse_turns_rule_based,
)


# --------- rule-based ---------


def _turn(idx: int, speaker: Speaker, text: str) -> Turn:
    return Turn(
        turn_id=f"t{idx}",
        session_id="s",
        speaker=speaker,
        content=text,
        timestamp=datetime.utcnow(),
    )


def test_turn_statistics_counts_and_length():
    turns = [
        _turn(0, Speaker.AI, "안녕, 오늘 광합성 이야기할까?"),
        _turn(1, Speaker.STUDENT, "광합성은 식물이 빛을 이용해 에너지를 만드는 거야."),
        _turn(2, Speaker.AI, "아 그래? 그럼 흙에서는 뭘 얻어?"),
        _turn(3, Speaker.STUDENT, "흙에서는 물하고 무기질을 얻어."),
    ]
    rubric = [
        RubricItem(item_id="r_light", description="빛 언급", keywords=["빛", "햇빛"]),
        RubricItem(item_id="r_water", description="물 언급", keywords=["물"]),
        RubricItem(item_id="r_nope", description="없는 키워드", keywords=["우주선"]),
    ]
    res = analyse_turns_rule_based(turns, rubric)

    assert res.turn_statistics.total_turns == 4
    assert res.turn_statistics.student.turn_count == 2
    assert res.turn_statistics.ai.turn_count == 2
    assert res.turn_statistics.ai.question_count >= 1  # AI asked a question

    # Rubric: light + water matched from student turns, 'nope' not achieved.
    assert res.rubric_items_achieved["r_light"] is True
    assert res.rubric_items_achieved["r_water"] is True
    assert res.rubric_items_achieved["r_nope"] is False
    assert any(h.item_id == "r_light" for h in res.rubric_hits)
    # Keyword frequency populated.
    assert res.keyword_frequencies.get("빛", 0) >= 1
    assert res.keyword_frequencies.get("물", 0) >= 1


def test_hesitation_detected_only_for_student():
    turns = [
        _turn(0, Speaker.AI, "이게 아마 맞지 않아?"),  # should NOT count (AI)
        _turn(1, Speaker.STUDENT, "음... 잘 모르겠어."),
        _turn(2, Speaker.STUDENT, "뭔가 헷갈려."),
    ]
    res = analyse_turns_rule_based(turns, [])
    assert len(res.hesitation_markers) >= 2
    assert all(m.turn_index in {1, 2} for m in res.hesitation_markers)


def test_metacognitive_markers_detected():
    turns = [
        _turn(0, Speaker.STUDENT, "정리하면 광합성은 빛과 물이 필요해."),
        _turn(1, Speaker.STUDENT, "내가 방금 말한 거 다시 생각해보면, 흙은 양분이 아니야."),
    ]
    res = analyse_turns_rule_based(turns, [])
    assert len(res.metacognitive_markers) >= 2


def test_rubric_hit_excerpt_contains_keyword():
    turns = [
        _turn(
            0,
            Speaker.STUDENT,
            "식물은 햇빛을 받아서 광합성을 해. 햇빛이 매우 중요해.",
        )
    ]
    rubric = [RubricItem(item_id="r", description="빛", keywords=["햇빛"])]
    res = analyse_turns_rule_based(turns, rubric)
    assert len(res.rubric_hits) == 1
    hit = res.rubric_hits[0]
    assert "햇빛" in hit.first_turn_excerpt
    assert hit.hit_count == 2


def test_to_dict_is_json_serialisable():
    turns = [_turn(0, Speaker.STUDENT, "물하고 빛이 필요해.")]
    rubric = [RubricItem(item_id="r", description="물", keywords=["물"])]
    res = analyse_turns_rule_based(turns, rubric)
    d = res.to_dict()
    json.dumps(d, ensure_ascii=False)
    assert "turn_statistics" in d
    assert "rubric_items_achieved" in d


def test_patterns_are_non_empty():
    assert HESITATION_PATTERNS
    assert METACOGNITIVE_PATTERNS


# --------- orchestrator (with mocked Claude) ---------


class _Content:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Content(text)]


class _Messages:
    def __init__(self, replies_by_marker):
        self._replies = replies_by_marker
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        system = kwargs.get("system", "")
        # Route by system prompt marker
        for marker, reply in self._replies.items():
            if marker in system:
                return _Response(reply)
        return _Response("{}")


class StubAnthropicClient:
    def __init__(self, replies_by_marker):
        self.messages = _Messages(replies_by_marker)


@pytest.fixture
def completed_session(tmp_path, monkeypatch):
    db_path = tmp_path / "a.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())

    repo = SessionRepository()
    unit = UnitConfig(
        unit_code="u",
        subject="과학",
        unit_name="광합성",
        learning_goals=["광합성 조건"],
        rubric_items=[
            RubricItem(item_id="r_light", description="빛 언급", keywords=["빛"], required=True)
        ],
        common_misconceptions=["흙에서 양분"],
        persona_name="지후",
        persona_initial_misconceptions=["흙에서 양분"],
        instructor_name="김교수",
    )
    sid = repo.create_session(unit, "s01")

    # Add turns (student + ai)
    repo.append_turn(sid, Speaker.AI, "안녕, 광합성 얘기할까?")
    repo.append_turn(sid, Speaker.STUDENT, "광합성은 빛이 있어야 해.")
    repo.append_turn(sid, Speaker.AI, "흙에서는 뭘 해?")
    repo.append_turn(sid, Speaker.STUDENT, "흙에서는 물을 흡수해.")

    # Concept maps
    pre = ConceptMap(
        concepts=[Concept(id="c1", label="광합성"), Concept(id="c2", label="빛")],
        propositions=[Proposition(from_id="c1", to_id="c2", linking_phrase="의 조건은")],
    )
    post = ConceptMap(
        concepts=[
            Concept(id="c1", label="광합성"),
            Concept(id="c2", label="빛"),
            Concept(id="c3", label="물"),
        ],
        propositions=[
            Proposition(from_id="c1", to_id="c2", linking_phrase="의 조건은"),
            Proposition(from_id="c1", to_id="c3", linking_phrase="의 조건은"),
        ],
    )
    repo.save_pre_concept_map(sid, pre.model_dump(mode="json"))
    repo.save_post_concept_map(sid, post.model_dump(mode="json"))
    repo.save_initial_diagnosis(
        sid,
        {
            "level": "developing",
            "detected_misconceptions": [
                {"misconception": "흙에서 양분", "evidence_in_map": "c1-c3"}
            ],
        },
    )
    repo.save_reflection_answers(
        sid,
        {
            "q1_conceptual_change": "답" * 150,
            "q2_effective_question": "답" * 150,
            "q3_scaffolding": "답" * 150,
            "q4_counterfactual": "답" * 150,
            "q5_learning_by_teaching": "답" * 150,
        },
    )
    repo.complete_session(sid)

    yield sid, repo

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_orchestrator_happy_path_all_analyzers_succeed(completed_session):
    sid, repo = completed_session
    client = StubAnthropicClient(
        {
            "개념 변화": json.dumps(
                {
                    "trajectories": [
                        {
                            "misconception": "흙에서 양분",
                            "source": "student_initial",
                            "first_appearance_turn": 3,
                            "key_events": [],
                            "final_state": "partially_resolved",
                            "final_state_justification": "일부 교정됨",
                            "student_handling_strategy": "재설명",
                        }
                    ],
                    "overall_conceptual_change_summary": "학생이 흙의 역할을 명확히 하려 함.",
                },
                ensure_ascii=False,
            ),
            "Vygotsky 비계": json.dumps(
                {
                    "per_turn_assessment": [],
                    "fading_pattern": "partial_fading",
                    "overall_scaffolding_quality": "good",
                    "top_3_strong_scaffolding_moments": [],
                    "top_3_problematic_moments": [],
                },
                ensure_ascii=False,
            ),
            "Learning by Teaching": json.dumps(
                {
                    "explanation_quality_trajectory": [],
                    "pck_observations": {},
                    "first_vs_last_explanation_comparison": {
                        "early_excerpt": "",
                        "late_excerpt": "",
                        "observed_change": "명확해짐",
                    },
                    "strengths": ["빛 인식"],
                    "growth_points": ["흙 역할"],
                    "notable_moments": [],
                },
                ensure_ascii=False,
            ),
            "Novak": json.dumps(
                {
                    "changes_by_type": {
                        "addition": [{"concept": "물", "note": "새로 추가"}]
                    },
                    "key_emerging_cross_links": [],
                    "hierarchy_change_summary": "깊어짐",
                    "overall_learning_evidence": [],
                    "concerns": "",
                },
                ensure_ascii=False,
            ),
            "성찰저널": json.dumps(
                {
                    "per_question_analysis": [],
                    "cross_question_patterns": "일관됨",
                    "research_value_notes": "의미 있음",
                },
                ensure_ascii=False,
            ),
        }
    )

    bundle = run_full_analysis(sid, repo=repo, claude_client=client)

    # Every analyzer should have returned non-error output.
    assert bundle.rule_based
    assert "trajectories" in bundle.misconceptions
    assert bundle.scaffolding_quality.get("overall_scaffolding_quality") == "good"
    assert bundle.explanation_quality.get("strengths") == ["빛 인식"]
    # Concept map change includes both LLM content AND a guaranteed score_change
    assert bundle.concept_map_change.get("score_change") is not None
    assert "per_question_analysis" in bundle.reflection
    assert bundle.errors == []

    # Persisted on session row
    row = repo.get_session(sid)
    assert row.analysis_json is not None
    assert row.analysis_json["unit_code"] == "u"


def test_orchestrator_resilient_to_llm_failures(completed_session):
    sid, repo = completed_session

    class FailingMessages:
        def create(self, **kwargs):
            raise RuntimeError("network boom")

    class FailingClient:
        messages = FailingMessages()

    bundle = run_full_analysis(sid, repo=repo, claude_client=FailingClient())

    # Rule-based still succeeds.
    assert bundle.rule_based
    # Each LLM section has an _error but doesn't crash orchestrator.
    for section_name in (
        "misconceptions",
        "scaffolding_quality",
        "explanation_quality",
        "reflection",
    ):
        section = getattr(bundle, section_name)
        assert "_error" in section
    # Errors list aggregates them.
    assert len(bundle.errors) >= 4
    # Row has analysis_json regardless of LLM failures.
    assert repo.get_session(sid).analysis_json is not None


def test_orchestrator_skips_concept_map_change_without_maps(tmp_path, monkeypatch):
    db_path = tmp_path / "b.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())

    repo = SessionRepository()
    unit = UnitConfig(
        unit_code="u2",
        subject="과학",
        unit_name="짧은 세션",
        learning_goals=[],
        rubric_items=[],
        persona_name="동료",
        instructor_name="김교수",
    )
    sid = repo.create_session(unit, "s01")
    repo.complete_session(sid)

    bundle = run_full_analysis(
        sid,
        repo=repo,
        claude_client=StubAnthropicClient({}),  # LLMs return "{}"
    )
    assert "_error" in bundle.concept_map_change
    assert "개념도" in bundle.concept_map_change["_error"]
