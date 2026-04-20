"""Tests for the visual concept map editor's JSON parser."""

from __future__ import annotations

import json

import pytest

from src.ui.concept_map_editor import parse_visual_concept_map


def _sample_state() -> str:
    return json.dumps(
        {
            "concepts": [
                {"id": 1, "label": "광합성"},
                {"id": 2, "label": "빛"},
                {"id": 3, "label": "엽록체"},
            ],
            "propositions": [
                {"from_id": 1, "to_id": 2, "linking_phrase": "의 조건은"},
                {"from_id": 1, "to_id": 3, "linking_phrase": "이 일어나는 곳"},
            ],
            "cross_links": [
                {"from_id": 3, "to_id": 2, "linking_phrase": "가 흡수함"},
            ],
            "examples": [
                {"concept_id": 1, "text": "해바라기"},
            ],
        }
    )


def test_parse_happy_path():
    cmap = parse_visual_concept_map(_sample_state())
    assert len(cmap.concepts) == 3
    assert {c.label for c in cmap.concepts} == {"광합성", "빛", "엽록체"}
    assert len(cmap.propositions) == 2
    assert len(cmap.cross_links) == 1
    assert len(cmap.examples) == 1


def test_parse_empty_raises():
    with pytest.raises(ValueError, match="개념도가 비어있"):
        parse_visual_concept_map("")


def test_parse_no_concepts_raises():
    with pytest.raises(ValueError, match="개념이 하나도 없"):
        parse_visual_concept_map(json.dumps({"concepts": []}))


def test_parse_invalid_json_raises():
    with pytest.raises(ValueError, match="파싱 실패"):
        parse_visual_concept_map("{not valid json")


def test_parse_drops_edges_with_unknown_ids():
    state = json.dumps(
        {
            "concepts": [{"id": 1, "label": "A"}],
            "propositions": [
                # id 2 doesn't exist — should be silently dropped
                {"from_id": 1, "to_id": 2, "linking_phrase": "r"},
            ],
        }
    )
    cmap = parse_visual_concept_map(state)
    assert len(cmap.concepts) == 1
    assert cmap.propositions == []


def test_parse_drops_edges_with_empty_linking():
    state = json.dumps(
        {
            "concepts": [
                {"id": 1, "label": "A"},
                {"id": 2, "label": "B"},
            ],
            "propositions": [
                {"from_id": 1, "to_id": 2, "linking_phrase": ""},  # empty linking
            ],
        }
    )
    cmap = parse_visual_concept_map(state)
    assert cmap.propositions == []


def test_parse_translates_integer_ids_to_string():
    cmap = parse_visual_concept_map(_sample_state())
    # Pydantic Concept requires string id
    for c in cmap.concepts:
        assert isinstance(c.id, str)
        assert c.id.startswith("c")
