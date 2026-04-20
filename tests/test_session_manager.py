"""Tests for SessionManager: login, resume, lock."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config.settings import get_settings
from src.db.database import Base, get_engine, get_session_factory
from src.db.repository import SessionRepository
from src.services.session_manager import (
    AuthenticationError,
    SessionLockedError,
    SessionManager,
)


class StubClaude:
    """No-network stand-in that returns canned replies."""

    def __init__(self):
        self.calls = 0

    def generate_response(self, system_prompt: str, history, **_):
        self.calls += 1
        if not history:
            return f"[AI 오프닝 #{self.calls}]"
        return f"[AI 응답 #{self.calls}]"


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Point the app at a fresh SQLite DB and a temp configs dir."""

    # Redirect DB
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    # Drop + recreate tables cleanly
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())

    # Build a configs dir with one unit containing a known account.
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "test-unit.yaml").write_text(
        yaml.safe_dump(
            {
                "unit_code": "t-01",
                "subject": "과학",
                "unit_name": "테스트단원",
                "learning_goals": ["개념 A"],
                "rubric_items": [
                    {
                        "item_id": "r1",
                        "description": "A를 설명",
                        "keywords": ["A"],
                        "required": True,
                    }
                ],
                "common_misconceptions": ["오개념 1"],
                "persona_name": "지후",
                "persona_initial_misconceptions": ["오개념 1"],
                "instructor_name": "김교수",
                "student_accounts": [
                    {"id": "s01", "password": "abc12"},
                    {"id": "s02", "password": "xy9z3"},
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    yield configs_dir

    # Cleanup caches so next test starts clean
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def _manager(configs_dir: Path) -> SessionManager:
    return SessionManager(
        repo=SessionRepository(),
        claude=StubClaude(),
        configs_dir=configs_dir,
    )


def test_login_creates_session_and_opening_turn(isolated_env):
    mgr = _manager(isolated_env)
    result = mgr.login("t-01", "s01", "abc12")
    assert result.is_new is True
    assert result.session_id
    assert len(result.turns) == 1
    assert "AI 오프닝" in result.turns[0].content


def test_login_wrong_password(isolated_env):
    mgr = _manager(isolated_env)
    with pytest.raises(AuthenticationError):
        mgr.login("t-01", "s01", "wrong")


def test_login_unknown_unit(isolated_env):
    mgr = _manager(isolated_env)
    with pytest.raises(AuthenticationError):
        mgr.login("nope", "s01", "abc12")


def test_resume_mid_session(isolated_env):
    mgr = _manager(isolated_env)
    r1 = mgr.login("t-01", "s01", "abc12")
    mgr.submit_student_turn(r1.session_id, "설명 시도 1")
    # Same credentials again — should resume, not create new.
    r2 = mgr.login("t-01", "s01", "abc12")
    assert r2.is_new is False
    assert r2.session_id == r1.session_id
    assert len(r2.turns) >= 3  # opening + student + ai reply


def test_completed_session_is_locked(isolated_env):
    mgr = _manager(isolated_env)
    r1 = mgr.login("t-01", "s01", "abc12")
    mgr.complete_session(r1.session_id)
    with pytest.raises(SessionLockedError):
        mgr.login("t-01", "s01", "abc12")


def test_cannot_submit_turn_to_completed_session(isolated_env):
    mgr = _manager(isolated_env)
    r1 = mgr.login("t-01", "s01", "abc12")
    mgr.complete_session(r1.session_id)
    with pytest.raises(SessionLockedError):
        mgr.submit_student_turn(r1.session_id, "더 설명")


def test_two_students_get_separate_sessions(isolated_env):
    mgr = _manager(isolated_env)
    r1 = mgr.login("t-01", "s01", "abc12")
    r2 = mgr.login("t-01", "s02", "xy9z3")
    assert r1.session_id != r2.session_id
