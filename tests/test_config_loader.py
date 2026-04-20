"""Tests for the YAML unit-config loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.unit_config import (
    UnitConfigError,
    find_unit_config_by_code,
    load_unit_config,
)
from src.models.enums import GradeLevel, HintType


EXAMPLE_PATH = Path("configs") / "example_elementary_photosynthesis.yaml"


def test_load_example_elementary_config():
    cfg = load_unit_config(EXAMPLE_PATH)

    assert cfg.session_code == "photo-g6-0420"
    assert cfg.grade_level == GradeLevel.ELEMENTARY
    assert cfg.unit_name == "광합성"
    assert cfg.persona_name == "수아"
    assert cfg.hint_max_count == 3
    assert HintType.BRIDGING in cfg.hint_types_allowed
    assert any(item.item_id == "condition_light" for item in cfg.rubric_items)
    # Required rubric items default to True unless explicitly set.
    light = next(i for i in cfg.rubric_items if i.item_id == "condition_light")
    assert light.required is True


def test_find_by_session_code():
    cfg = find_unit_config_by_code("photo-g6-0420", "configs")
    assert cfg.unit_name == "광합성"


def test_find_by_session_code_missing():
    with pytest.raises(UnitConfigError):
        find_unit_config_by_code("does-not-exist-xyz", "configs")


def test_load_missing_file(tmp_path):
    with pytest.raises(UnitConfigError):
        load_unit_config(tmp_path / "nope.yaml")


def test_load_invalid_yaml_top_level(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(UnitConfigError):
        load_unit_config(bad)


def test_load_invalid_schema(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "session_code: x\n"
        "grade_level: unknown_level\n"  # invalid enum
        "subject: 과학\n"
        "unit_name: test\n"
        "learning_goals: []\n"
        "rubric_items: []\n"
        "persona_name: a\n"
        "persona_role: b\n"
        "teacher_email: t@e.kr\n"
        "teacher_name: t\n",
        encoding="utf-8",
    )
    with pytest.raises(UnitConfigError):
        load_unit_config(bad)
