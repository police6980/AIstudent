"""Tests for the YAML unit-config loader and authentication."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.unit_config import (
    UnitConfigError,
    authenticate,
    find_unit_config_by_code,
    list_all_unit_codes,
    load_unit_config,
)
from src.models.enums import HintType
from src.models.schemas import StudentAccount


EXAMPLE_PATH = Path("configs") / "example_photosynthesis.yaml"


def test_load_example_config():
    cfg = load_unit_config(EXAMPLE_PATH)

    assert cfg.unit_code == "photo-01"
    assert cfg.unit_name == "광합성"
    assert cfg.persona_name == "지후"
    assert cfg.target_grade_for_teaching == "초등 6학년"
    assert cfg.hint_max_count == 3
    assert HintType.SOCRATIC in cfg.hint_types_allowed
    assert any(item.item_id == "condition_light" for item in cfg.rubric_items)
    # Example YAML does not ship with student_accounts (those are generated per deployment).
    assert cfg.student_accounts == []


def test_find_by_unit_code():
    cfg = find_unit_config_by_code("photo-01", "configs")
    assert cfg.unit_name == "광합성"


def test_find_by_unit_code_missing():
    with pytest.raises(UnitConfigError):
        find_unit_config_by_code("does-not-exist-xyz", "configs")


def test_list_all_unit_codes_contains_example():
    codes = list_all_unit_codes("configs")
    assert "photo-01" in codes


def test_load_missing_file(tmp_path):
    with pytest.raises(UnitConfigError):
        load_unit_config(tmp_path / "nope.yaml")


def test_load_invalid_yaml_top_level(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(UnitConfigError):
        load_unit_config(bad)


def test_load_missing_required_field(tmp_path):
    # Missing unit_code / unit_name / learning_goals / persona_name / instructor_name etc.
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "unit_name: test\n"
        "subject: 과학\n"
        "learning_goals: []\n"
        "rubric_items: []\n"
        "persona_name: 지후\n"
        "instructor_name: 김교수\n",
        encoding="utf-8",
    )
    with pytest.raises(UnitConfigError):
        load_unit_config(bad)


def test_authenticate_happy_path():
    cfg = find_unit_config_by_code("photo-01", "configs")
    cfg = cfg.model_copy(
        update={"student_accounts": [StudentAccount(id="s01", password="abc12")]}
    )
    assert authenticate(cfg, "s01", "abc12") is True


def test_authenticate_wrong_password():
    cfg = find_unit_config_by_code("photo-01", "configs")
    cfg = cfg.model_copy(
        update={"student_accounts": [StudentAccount(id="s01", password="abc12")]}
    )
    assert authenticate(cfg, "s01", "xxxxx") is False


def test_authenticate_unknown_id():
    cfg = find_unit_config_by_code("photo-01", "configs")
    cfg = cfg.model_copy(
        update={"student_accounts": [StudentAccount(id="s01", password="abc12")]}
    )
    assert authenticate(cfg, "s99", "abc12") is False


def test_authenticate_empty_inputs_rejected():
    cfg = find_unit_config_by_code("photo-01", "configs")
    cfg = cfg.model_copy(
        update={"student_accounts": [StudentAccount(id="s01", password="abc12")]}
    )
    assert authenticate(cfg, "", "abc12") is False
    assert authenticate(cfg, "s01", "") is False
