"""Tests for instructor-side services (auth, unit CRUD, session browsing)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config.settings import get_settings
from src.db.database import Base, get_engine, get_session_factory
from src.db.repository import SessionRepository
from src.models.enums import SessionStatus
from src.models.schemas import RubricItem, UnitConfig
from src.services.instructor_service import (
    admin_enabled,
    delete_reference,
    delete_unit,
    list_sessions,
    list_units,
    reset_session_to_in_progress,
    save_reference_upload,
    save_unit_config,
    verify_instructor_password,
)


# ---- auth ----


def test_admin_disabled_when_env_unset(monkeypatch):
    monkeypatch.delenv("INSTRUCTOR_PASSWORD", raising=False)
    get_settings.cache_clear()
    assert not admin_enabled()
    assert not verify_instructor_password("anything")


def test_admin_enabled_and_password_matches(monkeypatch):
    monkeypatch.setenv("INSTRUCTOR_PASSWORD", "sekret")
    get_settings.cache_clear()
    assert admin_enabled()
    assert verify_instructor_password("sekret")
    assert not verify_instructor_password("wrong")


def test_blank_password_disables_admin(monkeypatch):
    monkeypatch.setenv("INSTRUCTOR_PASSWORD", "   ")
    get_settings.cache_clear()
    assert not admin_enabled()


# ---- unit CRUD ----


def _make_unit(code: str = "u-test") -> UnitConfig:
    return UnitConfig(
        unit_code=code,
        subject="과학",
        unit_name="테스트",
        learning_goals=["목표 A"],
        rubric_items=[
            RubricItem(item_id="r1", description="A 설명", keywords=["A"], required=True)
        ],
        common_misconceptions=["오개념 1"],
        persona_name="지후",
        persona_initial_misconceptions=["오개념 1"],
        instructor_name="김교수",
    )


def test_save_unit_roundtrip(tmp_path):
    cfg = _make_unit("u-round")
    path = save_unit_config(cfg, configs_dir=tmp_path)
    assert path.exists()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["unit_code"] == "u-round"
    assert loaded["learning_goals"] == ["목표 A"]


def test_list_units_reads_only_valid_yamls(tmp_path):
    save_unit_config(_make_unit("u-a"), configs_dir=tmp_path)
    save_unit_config(_make_unit("u-b"), configs_dir=tmp_path)
    (tmp_path / "broken.yaml").write_text("just a string", encoding="utf-8")

    units = list_units(configs_dir=tmp_path)
    codes = {u.unit_code for u in units}
    assert codes == {"u-a", "u-b"}


def test_delete_unit_removes_file_and_sidecar(tmp_path):
    cfg = _make_unit("u-del")
    path = save_unit_config(cfg, configs_dir=tmp_path)
    sidecar = path.with_suffix(".accounts.txt")
    sidecar.write_text("accounts", encoding="utf-8")

    delete_unit(path.name, configs_dir=tmp_path)
    assert not path.exists()
    assert not sidecar.exists()


# ---- reference material upload ----


def test_save_reference_upload(tmp_path, monkeypatch):
    # Redirect the reference dir
    target = tmp_path / "refs"
    monkeypatch.chdir(tmp_path)

    src = tmp_path / "source.md"
    src.write_text("hello", encoding="utf-8")

    saved = save_reference_upload(src, "my_notes.md")
    assert saved.name == "my_notes.md"
    assert saved.read_text(encoding="utf-8") == "hello"
    # Ensure the helper created it under configs/reference_materials relative to cwd
    assert saved.parent.name == "reference_materials"

    # Cleanup
    delete_reference("my_notes.md")
    assert not saved.exists()


# ---- session browsing ----


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "i.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_list_sessions_and_reset(isolated_db):
    repo = SessionRepository()
    cfg = _make_unit("u-session")
    sid = repo.create_session(cfg, "s01")
    repo.complete_session(sid)

    sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].status == SessionStatus.COMPLETED
    assert sessions[0].student_id == "s01"

    reset_session_to_in_progress(sid)
    sessions = list_sessions()
    assert sessions[0].status == SessionStatus.IN_PROGRESS
    assert sessions[0].end_time is None


def test_list_sessions_filter_by_unit(isolated_db):
    repo = SessionRepository()
    repo.create_session(_make_unit("u-A"), "s01")
    repo.create_session(_make_unit("u-B"), "s01")

    only_a = list_sessions(unit_code="u-A")
    assert len(only_a) == 1
    assert only_a[0].unit_code == "u-A"


def test_reset_missing_session(isolated_db):
    with pytest.raises(LookupError):
        reset_session_to_in_progress("does-not-exist")
