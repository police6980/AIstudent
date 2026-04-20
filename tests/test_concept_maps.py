"""Tests for B1: concept map schema, hierarchy, Novak scoring, diagnosis, UI parsing."""

from __future__ import annotations

import pytest

from src.models.concept_map import (
    Concept,
    ConceptMap,
    CrossLink,
    Example,
    Proposition,
)
from src.services.concept_maps.novak_scoring import (
    DEFAULT_WEIGHTS,
    compute_hierarchy,
    score_concept_map,
)
from src.ui.concept_map_ui import (
    ConceptMapParseError,
    build_concept_map_from_inputs,
)


# ---------- schema ----------


def test_concept_map_rejects_empty_labels():
    with pytest.raises(Exception):
        Concept(id="c1", label="   ")


def test_proposition_rejects_empty_linking():
    with pytest.raises(Exception):
        Proposition(from_id="c1", to_id="c2", linking_phrase="")


def test_validate_references_flags_missing_ids():
    cmap = ConceptMap(
        concepts=[Concept(id="c1", label="A"), Concept(id="c2", label="B")],
        propositions=[Proposition(from_id="c1", to_id="cX", linking_phrase="rel")],
        cross_links=[CrossLink(from_id="cY", to_id="c1", linking_phrase="rel")],
        examples=[Example(concept_id="cZ", text="ex")],
    )
    problems = cmap.validate_references()
    joined = " ".join(problems)
    assert "cX" in joined
    assert "cY" in joined
    assert "cZ" in joined


def test_validate_references_flags_self_loops():
    cmap = ConceptMap(
        concepts=[Concept(id="c1", label="A")],
        propositions=[Proposition(from_id="c1", to_id="c1", linking_phrase="r")],
    )
    problems = cmap.validate_references()
    assert any("같아요" in p for p in problems)


# ---------- hierarchy inference ----------


def test_hierarchy_simple_chain():
    cmap = ConceptMap(
        concepts=[Concept(id=f"c{i}", label=f"L{i}") for i in range(1, 4)],
        propositions=[
            Proposition(from_id="c1", to_id="c2", linking_phrase="r"),
            Proposition(from_id="c2", to_id="c3", linking_phrase="r"),
        ],
    )
    h = compute_hierarchy(cmap)
    assert h.concept_levels == {"c1": 1, "c2": 2, "c3": 3}
    assert h.max_level == 3
    assert h.roots == ["c1"]
    assert not h.cycles_present
    assert h.isolated_concepts == []


def test_hierarchy_with_isolated_concept():
    cmap = ConceptMap(
        concepts=[
            Concept(id="c1", label="A"),
            Concept(id="c2", label="B"),
            Concept(id="c3", label="lonely"),
        ],
        propositions=[Proposition(from_id="c1", to_id="c2", linking_phrase="r")],
    )
    h = compute_hierarchy(cmap)
    assert "c3" in h.isolated_concepts
    assert h.concept_levels.get("c3") is None  # isolated -> not leveled


def test_hierarchy_handles_cycle():
    cmap = ConceptMap(
        concepts=[Concept(id=f"c{i}", label=f"L{i}") for i in range(1, 4)],
        propositions=[
            Proposition(from_id="c1", to_id="c2", linking_phrase="r"),
            Proposition(from_id="c2", to_id="c3", linking_phrase="r"),
            Proposition(from_id="c3", to_id="c1", linking_phrase="r"),  # cycle
        ],
    )
    h = compute_hierarchy(cmap)
    assert h.cycles_present is True
    # Entire cycle collapses to a single SCC = one level, so max_level == 1
    assert h.max_level == 1


def test_cross_link_endpoint_not_counted_as_isolated():
    cmap = ConceptMap(
        concepts=[
            Concept(id="c1", label="A"),
            Concept(id="c2", label="B"),
            Concept(id="c3", label="C"),
        ],
        propositions=[Proposition(from_id="c1", to_id="c2", linking_phrase="r")],
        cross_links=[CrossLink(from_id="c1", to_id="c3", linking_phrase="cr")],
    )
    h = compute_hierarchy(cmap)
    # c3 has no propositions but IS connected via cross-link → not isolated
    assert "c3" not in h.isolated_concepts


# ---------- Novak scoring ----------


def test_score_basic_map():
    cmap = ConceptMap(
        concepts=[Concept(id=f"c{i}", label=f"L{i}") for i in range(1, 5)],
        propositions=[
            Proposition(from_id="c1", to_id="c2", linking_phrase="r"),
            Proposition(from_id="c1", to_id="c3", linking_phrase="r"),
            Proposition(from_id="c3", to_id="c4", linking_phrase="r"),
        ],
        cross_links=[CrossLink(from_id="c2", to_id="c4", linking_phrase="cr")],
        examples=[Example(concept_id="c4", text="ex1")],
    )
    score = score_concept_map(cmap)
    # 3 propositions * 1 + 3 levels * 5 + 1 cross_link * 10 + 1 example * 1
    # - 0 isolated - 0 misconception = 3 + 15 + 10 + 1 = 29
    assert score.valid_proposition_count == 3
    assert score.max_hierarchy_level == 3
    assert score.cross_link_count == 1
    assert score.example_count == 1
    assert score.total == 29.0


def test_score_applies_custom_weights():
    cmap = ConceptMap(
        concepts=[Concept(id="c1", label="A"), Concept(id="c2", label="B")],
        propositions=[Proposition(from_id="c1", to_id="c2", linking_phrase="r")],
    )
    # Override: cross-link worth 100 (though we have none here).
    # More practically: proposition weight 2.
    custom = {"proposition": 2.0}
    score = score_concept_map(cmap, weights=custom)
    # 1 prop * 2 + 2 levels * 5 (default) = 2 + 10 = 12
    assert score.total == 12.0
    assert score.weights_used["proposition"] == 2.0
    assert score.weights_used["hierarchy_level"] == DEFAULT_WEIGHTS["hierarchy_level"]


def test_score_penalises_isolated_and_misconceptions():
    cmap = ConceptMap(
        concepts=[
            Concept(id="c1", label="A"),
            Concept(id="c2", label="B"),
            Concept(id="c3", label="lone"),
        ],
        propositions=[Proposition(from_id="c1", to_id="c2", linking_phrase="r")],
    )
    score = score_concept_map(cmap, misconception_count=2)
    # 1 prop (1) + 2 levels (10) + 1 isolated (-2) + 2 misconceptions (-10)
    # = 1 + 10 - 2 - 10 = -1
    assert score.total == -1.0


# ---------- UI parsing ----------


def test_parse_full_block_happy_path():
    concepts_text = "광합성\n빛\n물\n엽록체\n포도당"
    propositions_text = (
        "광합성 | 의 조건은 | 빛\n"
        "광합성 | 의 조건은 | 물\n"
        "광합성 | 이 일어나는 장소는 | 엽록체\n"
        "광합성 | 의 산물은 | 포도당\n"
    )
    cross_text = "엽록체 | 가 흡수하는 | 빛\n"
    examples_text = "포도당 | 설탕은 식물이 만든 포도당의 변형\n"

    result = build_concept_map_from_inputs(
        concepts_text, propositions_text, cross_text, examples_text
    )
    assert len(result.concept_map.concepts) == 5
    assert len(result.concept_map.propositions) == 4
    assert len(result.concept_map.cross_links) == 1
    assert len(result.concept_map.examples) == 1
    assert result.warnings == []


def test_parse_empty_concepts_raises():
    with pytest.raises(ConceptMapParseError):
        build_concept_map_from_inputs("", "", "", "")


def test_parse_unknown_labels_warn_not_raise():
    concepts_text = "A\nB"
    proposition_text = "A | rel | C"  # C is unknown
    result = build_concept_map_from_inputs(concepts_text, proposition_text, "", "")
    assert result.concept_map.propositions == []  # skipped
    assert any("C" in w for w in result.warnings)


def test_parse_malformed_proposition_line_warns():
    concepts_text = "A\nB"
    proposition_text = "A - rel - B"  # wrong separator
    result = build_concept_map_from_inputs(concepts_text, proposition_text, "", "")
    assert result.concept_map.propositions == []
    assert any("|" in w or "요소" in w for w in result.warnings)


def test_parse_examples_require_two_fields():
    result = build_concept_map_from_inputs("A", "", "", "A only one field\nA | good ex")
    assert len(result.concept_map.examples) == 1
    assert result.concept_map.examples[0].text == "good ex"
    assert any("형식" in w for w in result.warnings)


def test_parse_duplicate_concept_labels_dedup():
    result = build_concept_map_from_inputs("A\nA\nB", "", "", "")
    labels = [c.label for c in result.concept_map.concepts]
    assert labels == ["A", "B"]
