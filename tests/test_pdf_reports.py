"""Tests for B5: PDF fonts, chart rendering, end-to-end PDF generation."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.config.settings import get_settings
from src.db.database import Base, get_engine, get_session_factory
from src.db.repository import SessionRepository
from src.models.concept_map import Concept, ConceptMap, Proposition
from src.models.enums import Speaker
from src.models.schemas import RubricItem, UnitConfig
from src.services.pdf.charts import (
    render_explanation_trajectory,
    render_misconception_states,
    render_novak_score_bars,
    render_rubric_donut,
)
from src.services.pdf.fonts import register_korean_font
from src.services.pdf.generator import generate_reports_for_session


# --------- fonts ---------


def test_register_korean_font_returns_two_names():
    regular, bold = register_korean_font()
    assert isinstance(regular, str) and regular
    assert isinstance(bold, str) and bold


# --------- charts ---------


def test_novak_score_bars_returns_png():
    data = render_novak_score_bars(pre_score=12.0, post_score=25.0)
    assert data.startswith(b"\x89PNG")


def test_rubric_donut_empty_map():
    data = render_rubric_donut({})
    assert data.startswith(b"\x89PNG")


def test_rubric_donut_partial():
    data = render_rubric_donut({"a": True, "b": False, "c": True})
    assert data.startswith(b"\x89PNG")


def test_misconception_states_handles_empty():
    data = render_misconception_states([])
    assert data.startswith(b"\x89PNG")


def test_misconception_states_with_mixed_states():
    data = render_misconception_states(
        [
            {"final_state": "resolved"},
            {"final_state": "partially_resolved"},
            {"final_state": "unresolved"},
            {"final_state": "newly_emerged"},
            {"final_state": "resolved"},
        ]
    )
    assert data.startswith(b"\x89PNG")


def test_explanation_trajectory_empty():
    data = render_explanation_trajectory([])
    assert data.startswith(b"\x89PNG")


def test_explanation_trajectory_with_segments():
    data = render_explanation_trajectory(
        [
            {"clarity": 2, "depth": 1, "structure": 2},
            {"clarity": 3, "depth": 2, "structure": 3},
            {"clarity": 4, "depth": 4, "structure": 4},
        ]
    )
    assert data.startswith(b"\x89PNG")


# --------- end-to-end generator ---------


@pytest.fixture
def seeded_session(tmp_path, monkeypatch):
    """A completed session with concept maps, dialogue, analysis, and reflections."""

    db_path = tmp_path / "pdf.db"
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("REPORT_DIR", str(report_dir))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())

    repo = SessionRepository()
    unit = UnitConfig(
        unit_code="u-pdf",
        subject="과학",
        unit_name="광합성",
        target_grade_for_teaching="초등 6학년",
        learning_goals=["광합성의 조건", "광합성의 산물"],
        rubric_items=[
            RubricItem(item_id="r_light", description="빛을 설명", keywords=["빛"]),
            RubricItem(item_id="r_water", description="물을 설명", keywords=["물"]),
        ],
        common_misconceptions=["식물은 흙에서 양분을 흡수"],
        persona_name="지후",
        persona_initial_misconceptions=["식물은 흙에서 양분을 흡수"],
        instructor_name="김교수",
    )
    sid = repo.create_session(unit, "s01")
    # Some turns
    repo.append_turn(sid, Speaker.AI, "안녕, 광합성 얘기 해볼까?")
    repo.append_turn(sid, Speaker.STUDENT, "광합성은 빛이 있어야 해.")
    repo.append_turn(sid, Speaker.AI, "흙에서는 뭘 얻어?")
    repo.append_turn(sid, Speaker.STUDENT, "흙에서는 물과 무기질을 얻어.")

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
            "level_justification": "일부 오개념 포함.",
            "detected_misconceptions": [
                {"misconception": "흙에서 양분", "evidence_in_map": "c1-c3 명제"}
            ],
            "missing_core_concepts": ["엽록체"],
            "strong_points": ["빛 인식"],
            "zpd_targets": ["양분 재개념화"],
            "recommended_first_question": "흙이 하는 일이 뭘까?",
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
    repo.save_analysis(
        sid,
        {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "session_id": sid,
            "student_id": "s01",
            "unit_code": "u-pdf",
            "rule_based": {
                "turn_statistics": {
                    "total_turns": 4,
                    "student": {"turn_count": 2, "avg_length": 10, "question_count": 0},
                    "ai": {"turn_count": 2, "avg_length": 8, "question_count": 1},
                },
                "rubric_items_achieved": {"r_light": True, "r_water": True},
                "rubric_hits": [
                    {
                        "item_id": "r_light",
                        "first_turn_index": 1,
                        "keyword_matched": "빛",
                        "first_turn_excerpt": "광합성은 빛이 있어야 해.",
                        "hit_count": 1,
                    },
                    {
                        "item_id": "r_water",
                        "first_turn_index": 3,
                        "keyword_matched": "물",
                        "first_turn_excerpt": "흙에서는 물과 무기질을 얻어.",
                        "hit_count": 1,
                    },
                ],
                "hesitation_markers": [],
                "metacognitive_markers": [],
                "keyword_frequencies": {"빛": 1, "물": 1},
            },
            "misconceptions": {
                "trajectories": [
                    {
                        "misconception": "흙에서 양분",
                        "source": "student_initial",
                        "first_appearance_turn": 3,
                        "key_events": [
                            {"turn": 3, "speaker": "student", "event": "드러냄", "excerpt": "흙에서 물과 무기질"}
                        ],
                        "final_state": "partially_resolved",
                        "final_state_justification": "부분 교정",
                        "student_handling_strategy": "재설명",
                    }
                ],
                "overall_conceptual_change_summary": "학생의 흙 역할 이해가 명확해짐.",
            },
            "scaffolding_quality": {
                "fading_pattern": "partial_fading",
                "overall_scaffolding_quality": "good",
                "top_3_strong_scaffolding_moments": [{"turn": 2, "reason": "좋은 되묻기"}],
                "top_3_problematic_moments": [],
            },
            "explanation_quality": {
                "explanation_quality_trajectory": [
                    {"segment": 1, "turn_range": "1-2", "clarity": 3, "depth": 2, "structure": 3},
                    {"segment": 2, "turn_range": "3-4", "clarity": 4, "depth": 3, "structure": 4},
                ],
                "pck_observations": {
                    "learner_awareness": {"score": 3, "evidence": ["빛 설명"]},
                },
                "first_vs_last_explanation_comparison": {
                    "early_excerpt": "광합성은 빛",
                    "late_excerpt": "흙에서 물",
                    "observed_change": "더 구체화됨",
                },
                "strengths": ["빛 인식"],
                "growth_points": ["흙 역할"],
                "notable_moments": [
                    {"turn": 3, "excerpt": "흙에서는 물과 무기질을 얻어.", "why_notable": "오개념 교정 시도"}
                ],
            },
            "concept_map_change": {
                "score_change": {"pre": 7.0, "post": 12.0, "delta": 5.0},
                "changes_by_type": {
                    "addition": [{"concept": "물", "note": "추가됨"}],
                    "integration": [],
                    "correction": [],
                    "persistence": [],
                },
                "key_emerging_cross_links": [],
                "hierarchy_change_summary": "동일",
                "overall_learning_evidence": ["개념 추가"],
            },
            "reflection": {
                "per_question_analysis": [
                    {
                        "question_id": "q1_conceptual_change",
                        "metacognitive_depth": 3,
                        "evidence_grounding": 3,
                        "depth_of_insight": 3,
                        "self_observation_accuracy": "medium",
                        "key_quotes": [],
                        "analytic_summary": "학생의 개념 변화 인식이 명확.",
                    }
                ],
                "cross_question_patterns": "일관됨",
                "research_value_notes": "유의미함",
            },
            "errors": [],
        },
    )
    repo.complete_session(sid)

    yield sid, repo

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_generate_reports_produces_two_pdf_files(seeded_session):
    sid, repo = seeded_session
    paths = generate_reports_for_session(sid, repo=repo)

    assert paths.summary.exists()
    assert paths.detail.exists()

    # PDF magic bytes
    assert paths.summary.read_bytes().startswith(b"%PDF")
    assert paths.detail.read_bytes().startswith(b"%PDF")

    # Non-trivial size (should be at least a few KB)
    assert paths.summary.stat().st_size > 2000
    assert paths.detail.stat().st_size > 4000


def test_generate_reports_missing_session_raises(seeded_session):
    _sid, repo = seeded_session
    import pytest as _pt

    with _pt.raises(LookupError):
        generate_reports_for_session("does-not-exist", repo=repo)


def test_generate_reports_handles_empty_analysis(tmp_path, monkeypatch):
    """Even with empty analysis_json, PDF generation should not crash."""

    db_path = tmp_path / "empty.db"
    report_dir = tmp_path / "reports_e"
    report_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("REPORT_DIR", str(report_dir))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())

    repo = SessionRepository()
    unit = UnitConfig(
        unit_code="u-min",
        subject="과학",
        unit_name="최소",
        learning_goals=[],
        rubric_items=[],
        persona_name="지후",
        instructor_name="김교수",
    )
    sid = repo.create_session(unit, "s01")
    repo.complete_session(sid)

    paths = generate_reports_for_session(sid, repo=repo)
    assert paths.summary.exists()
    assert paths.detail.exists()
    assert paths.summary.read_bytes().startswith(b"%PDF")

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
