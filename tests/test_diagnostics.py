"""Tests for B0: reference loader, diagnostic config, prompt assembler, reflection loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.services.diagnostics.diagnostic_config import (
    DiagnosticConfigError,
    list_diagnostics,
    load_diagnostic,
    save_diagnostic,
)
from src.services.diagnostics.prompt_assembler import assemble_prompt
from src.services.diagnostics.reference_loader import (
    ReferenceMaterialError,
    format_materials_block,
    list_reference_materials,
    load_reference_material,
    load_reference_materials,
)
from src.services.diagnostics.reflection_loader import (
    ReflectionQuestion,
    load_reflection_questions,
    save_reflection_questions,
)


# ------------------ reference_loader ------------------

def test_list_bundled_reference_materials():
    names = list_reference_materials()
    assert "default_vygotsky.md" in names
    assert "default_novak.md" in names


def test_load_markdown_reference():
    m = load_reference_material("default_vygotsky.md")
    assert "ZPD" in m.text or "근접발달영역" in m.text
    assert m.title  # derived from H1
    assert not m.truncated  # bundled docs fit under limit


def test_load_missing_reference_raises():
    with pytest.raises(ReferenceMaterialError):
        load_reference_material("does_not_exist.md")


def test_load_unsupported_extension(tmp_path):
    p = tmp_path / "weird.xyz"
    p.write_text("hi", encoding="utf-8")
    with pytest.raises(ReferenceMaterialError):
        load_reference_material("weird.xyz", ref_dir=tmp_path)


def test_load_multiple_skips_missing():
    materials = load_reference_materials(
        ["default_vygotsky.md", "nope.md", "default_novak.md"]
    )
    assert len(materials) == 2  # missing one silently skipped


def test_format_materials_block_empty():
    assert "참고 자료 없음" in format_materials_block([])


def test_truncation_on_long_file(tmp_path):
    huge = tmp_path / "huge.md"
    huge.write_text("x" * 20000, encoding="utf-8")
    m = load_reference_material("huge.md", ref_dir=tmp_path)
    assert m.truncated
    assert "(이하 생략)" in m.text


# ------------------ diagnostic_config ------------------

def test_list_bundled_diagnostics():
    files = list_diagnostics()
    assert "concept_map_diagnosis.yaml" in files
    assert "misconception_tracking.yaml" in files
    assert "scaffolding_quality.yaml" in files


def test_load_concept_map_diagnosis():
    d = load_diagnostic("concept_map_diagnosis.yaml")
    assert d.name
    assert d.prompt_template
    assert "default_vygotsky.md" in d.reference_materials
    # extras include scoring_weights, level_rubric
    assert "scoring_weights" in d.extras
    assert "level_rubric" in d.extras


def test_load_invalid_diagnostic(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: only\n", encoding="utf-8")  # missing prompt_template
    with pytest.raises(DiagnosticConfigError):
        load_diagnostic("bad.yaml", diag_dir=tmp_path)


def test_save_and_reload_diagnostic(tmp_path):
    payload = {
        "name": "test diagnostic",
        "description": "a test",
        "reference_materials": [],
        "prompt_template": "hello {var}",
        "custom_field": 123,
    }
    save_diagnostic("test_diag.yaml", payload, diag_dir=tmp_path)
    d = load_diagnostic("test_diag.yaml", diag_dir=tmp_path)
    assert d.name == "test diagnostic"
    assert d.prompt_template == "hello {var}"
    assert d.extras["custom_field"] == 123


# ------------------ prompt_assembler ------------------

def test_assemble_prompt_substitutes_variables_and_materials(tmp_path):
    diag = load_diagnostic("concept_map_diagnosis.yaml")
    variables = {
        "unit_name": "광합성",
        "learning_goals": ["A", "B"],
        "common_misconceptions": ["오개념1"],
        "concept_count": 5,
        "concepts": ["광합성", "빛"],
        "proposition_count": 2,
        "propositions": ["광합성-의 조건은-빛"],
        "cross_link_count": 0,
        "cross_links": [],
        "example_count": 0,
        "examples": [],
        "max_hierarchy_level": 2,
        "isolated_concepts": [],
    }
    prompt = assemble_prompt(diag, variables)
    assert "광합성" in prompt
    assert "ZPD" in prompt or "근접발달영역" in prompt  # from vygotsky reference
    # rubric injected from extras
    assert "novice" in prompt or "developing" in prompt


def test_assemble_prompt_missing_variable_keeps_placeholder():
    diag = load_diagnostic("concept_map_diagnosis.yaml")
    # Intentionally provide nothing — missing keys should keep their placeholders,
    # not crash.
    prompt = assemble_prompt(diag, {})
    assert "{unit_name}" in prompt  # placeholder preserved


# ------------------ reflection_loader ------------------

def test_load_bundled_reflection_questions():
    qs = load_reflection_questions()
    assert len(qs) == 5
    ids = {q.id for q in qs}
    assert "q1_conceptual_change" in ids
    assert "q5_learning_by_teaching" in ids
    for q in qs:
        assert q.min_chars == 100
        assert q.prompt


def test_reflection_validate_answer():
    q = ReflectionQuestion(id="x", title="t", prompt="p", min_chars=10)
    ok, count = q.validate_answer("짧아")
    assert not ok
    assert count == 2
    ok, count = q.validate_answer("x" * 15)
    assert ok
    assert count == 15


def test_save_and_reload_reflection_roundtrip(tmp_path):
    path = tmp_path / "rq.yaml"
    originals = [
        ReflectionQuestion(id="a", title="제목A", prompt="본문A", min_chars=50),
        ReflectionQuestion(id="b", title="제목B", prompt="본문B", min_chars=200),
    ]
    save_reflection_questions(originals, path=path)
    loaded = load_reflection_questions(path=path)
    assert [q.id for q in loaded] == ["a", "b"]
    assert loaded[1].min_chars == 200


def test_duplicate_ids_rejected(tmp_path):
    path = tmp_path / "rq.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "questions": [
                    {"id": "same", "title": "t1", "prompt": "p1"},
                    {"id": "same", "title": "t2", "prompt": "p2"},
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_reflection_questions(path=path)
