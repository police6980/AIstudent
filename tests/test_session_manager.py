"""Tests for SessionManager: login, state machine, resume, lock."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.config.settings import get_settings
from src.db.database import Base, get_engine, get_session_factory
from src.db.repository import SessionRepository
from src.models.concept_map import Concept, ConceptMap, Proposition
from src.models.enums import SessionStatus, SessionStep
from src.services.session_manager import (
    AuthenticationError,
    SessionLockedError,
    SessionManager,
    StepViolationError,
)


class _Content:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Content(text)]


class _Messages:
    def __init__(self, reply_fn):
        self._reply_fn = reply_fn
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return _Response(self._reply_fn(self.calls, kwargs))


class StubAnthropicClient:
    """Stand-in for the anthropic.Anthropic client."""

    def __init__(self, reply_fn=None):
        reply_fn = reply_fn or (lambda i, _kw: f"[AI #{i}]")
        self.messages = _Messages(reply_fn)


class StubClaudeService:
    """Stand-in for ClaudeService used by SessionManager."""

    def __init__(self):
        self.calls = 0

    def generate_response(self, system_prompt: str, history, **_):
        self.calls += 1
        if not history:
            return f"[AI 오프닝 #{self.calls}]"
        return f"[AI 답변 #{self.calls}]"


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "t.yaml").write_text(
        yaml.safe_dump(
            {
                "unit_code": "t-01",
                "subject": "과학",
                "unit_name": "테스트",
                "learning_goals": ["A"],
                "rubric_items": [
                    {"item_id": "r1", "description": "A 설명", "keywords": ["A"], "required": True}
                ],
                "common_misconceptions": ["오개념"],
                "persona_name": "지후",
                "persona_initial_misconceptions": ["오개념"],
                "instructor_name": "김교수",
                "student_login_mode": "account_list",
                "student_accounts": [
                    {"id": "s01", "password": "abc12"},
                    {"id": "s02", "password": "xyz98"},
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    yield configs_dir

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def _valid_concept_map() -> ConceptMap:
    return ConceptMap(
        concepts=[Concept(id="c1", label="광합성"), Concept(id="c2", label="빛")],
        propositions=[Proposition(from_id="c1", to_id="c2", linking_phrase="의 조건은")],
    )


def _mgr(configs_dir: Path, monkeypatch):
    """Build a SessionManager whose diagnosis Claude client is also stubbed."""

    import src.services.concept_maps.diagnosis as diag_mod

    def fake_diagnose(concept_map, unit_config, **_kw):
        from src.services.concept_maps.diagnosis import InitialDiagnosis
        from src.services.concept_maps.novak_scoring import (
            compute_hierarchy,
            score_concept_map,
        )

        h = compute_hierarchy(concept_map)
        return InitialDiagnosis(
            level="developing",
            level_justification="stub",
            strong_points=["알고 있음"],
            zpd_targets=["더 깊은 연결"],
            recommended_first_question="여기서부터 설명해볼래?",
            novak_score=score_concept_map(concept_map, hierarchy=h),
            hierarchy=h,
        )

    monkeypatch.setattr(
        "src.services.session_manager.diagnose_initial_concept_map", fake_diagnose
    )

    return SessionManager(
        repo=SessionRepository(),
        claude=StubClaudeService(),
        configs_dir=configs_dir,
    )


# --------- login / step routing ---------


def test_login_creates_fresh_session_at_pre_map(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    result = mgr.login("t-01", "s01", "abc12")
    assert result.is_new is True
    assert result.current_step == SessionStep.PRE_MAP
    # No opening turn yet — AI waits for pre-map submission.
    assert result.turns == []


def test_login_wrong_password(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    with pytest.raises(AuthenticationError):
        mgr.login("t-01", "s01", "wrong")


# --------- PRE_MAP -> DIALOGUE ---------


def test_submit_pre_map_advances_and_opens_dialogue(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    result = mgr.submit_pre_concept_map(r.session_id, _valid_concept_map())
    assert result.next_step == SessionStep.DIALOGUE
    assert result.diagnosis is not None
    assert result.diagnosis.level == "developing"
    assert any("[AI" in t.content for t in result.turns)

    # DB persisted the map + diagnosis.
    row = mgr._repo.get_session(r.session_id)  # type: ignore[attr-defined]
    assert row.current_step == SessionStep.DIALOGUE.value
    assert row.pre_concept_map_json is not None
    assert row.initial_diagnosis_json is not None


def test_cannot_submit_pre_map_twice(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    mgr.submit_pre_concept_map(r.session_id, _valid_concept_map())
    with pytest.raises(StepViolationError):
        mgr.submit_pre_concept_map(r.session_id, _valid_concept_map())


# --------- DIALOGUE ---------


def test_cannot_send_turn_before_pre_map(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    with pytest.raises(StepViolationError):
        mgr.submit_student_turn(r.session_id, "뭐라고 설명해볼게")


def test_dialogue_round_trip(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    mgr.submit_pre_concept_map(r.session_id, _valid_concept_map())
    ai = mgr.submit_student_turn(r.session_id, "광합성은 빛이 필요해.")
    assert "AI" in ai.content


def test_end_dialogue_transitions_to_post_map(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    mgr.submit_pre_concept_map(r.session_id, _valid_concept_map())
    mgr.submit_student_turn(r.session_id, "설명 한 줄")
    mgr.end_dialogue(r.session_id)

    resumed = mgr.login("t-01", "s01", "abc12")
    assert resumed.current_step == SessionStep.POST_MAP


def test_cannot_end_dialogue_before_pre_map(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    with pytest.raises(StepViolationError):
        mgr.end_dialogue(r.session_id)


# --------- POST_MAP -> REFLECTION ---------


def test_submit_post_map_transitions_to_reflection(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    mgr.submit_pre_concept_map(r.session_id, _valid_concept_map())
    mgr.end_dialogue(r.session_id)

    next_step = mgr.submit_post_concept_map(r.session_id, _valid_concept_map())
    assert next_step == SessionStep.REFLECTION

    row = mgr._repo.get_session(r.session_id)  # type: ignore[attr-defined]
    assert row.post_concept_map_json is not None


# --------- REFLECTION -> COMPLETED ---------


def _make_reflection_answers(length: int = 150) -> dict[str, str]:
    # Fetch bundled reflection questions and fulfill each with a long enough answer.
    from src.services.diagnostics import load_reflection_questions

    qs = load_reflection_questions()
    return {q.id: "답" * max(length, q.min_chars + 5) for q in qs}


def test_submit_reflection_short_answer_rejected(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    mgr.submit_pre_concept_map(r.session_id, _valid_concept_map())
    mgr.end_dialogue(r.session_id)
    mgr.submit_post_concept_map(r.session_id, _valid_concept_map())

    # All answers too short (empty).
    with pytest.raises(ValueError) as exc:
        mgr.submit_reflection_answers(r.session_id, {})
    assert "자 이상" in str(exc.value)


def test_full_happy_path_completes_session(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    mgr.submit_pre_concept_map(r.session_id, _valid_concept_map())
    mgr.submit_student_turn(r.session_id, "여기가 내 설명")
    mgr.end_dialogue(r.session_id)
    mgr.submit_post_concept_map(r.session_id, _valid_concept_map())
    mgr.submit_reflection_answers(r.session_id, _make_reflection_answers())

    # Completed + locked.
    row = mgr._repo.get_session(r.session_id)  # type: ignore[attr-defined]
    assert row.status == SessionStatus.COMPLETED.value
    assert row.current_step == SessionStep.COMPLETED.value
    assert row.reflection_answers_json is not None

    with pytest.raises(SessionLockedError):
        mgr.login("t-01", "s01", "abc12")


def test_resume_at_current_step(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    r = mgr.login("t-01", "s01", "abc12")
    mgr.submit_pre_concept_map(r.session_id, _valid_concept_map())
    # Re-login mid-session
    resumed = mgr.login("t-01", "s01", "abc12")
    assert resumed.is_new is False
    assert resumed.current_step == SessionStep.DIALOGUE
    # The AI opening turn is visible on resume.
    assert any(t.content.startswith("[AI") for t in resumed.turns)


def test_two_students_independent_steps(isolated_env, monkeypatch):
    mgr = _mgr(isolated_env, monkeypatch)
    a = mgr.login("t-01", "s01", "abc12")
    b = mgr.login("t-01", "s02", "xyz98")
    assert a.session_id != b.session_id

    mgr.submit_pre_concept_map(a.session_id, _valid_concept_map())
    # s02 still at PRE_MAP.
    resumed_b = mgr.login("t-01", "s02", "xyz98")
    assert resumed_b.current_step == SessionStep.PRE_MAP


# --------- open login mode ---------


@pytest.fixture
def open_mode_env(tmp_path, monkeypatch):
    """Same setup as isolated_env but the unit uses student_login_mode: open."""

    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "open.yaml").write_text(
        yaml.safe_dump(
            {
                "unit_code": "open-01",
                "subject": "과학",
                "unit_name": "개방 단원",
                "learning_goals": ["A"],
                "rubric_items": [
                    {"item_id": "r1", "description": "A", "keywords": ["A"], "required": True}
                ],
                "common_misconceptions": ["x"],
                "persona_name": "지후",
                "persona_initial_misconceptions": ["x"],
                "instructor_name": "김교수",
                "student_login_mode": "open",
                # No student_accounts in open mode
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    yield configs_dir

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_open_mode_allows_anyone_with_student_id_and_name(open_mode_env, monkeypatch):
    mgr = _mgr(open_mode_env, monkeypatch)
    result = mgr.login("open-01", "2021001", student_name="홍길동")
    assert result.is_new is True
    assert result.session_id


def test_open_mode_requires_name(open_mode_env, monkeypatch):
    mgr = _mgr(open_mode_env, monkeypatch)
    with pytest.raises(AuthenticationError):
        mgr.login("open-01", "2021001")  # name missing


def test_open_mode_requires_student_id(open_mode_env, monkeypatch):
    mgr = _mgr(open_mode_env, monkeypatch)
    with pytest.raises(AuthenticationError):
        mgr.login("open-01", "", student_name="홍길동")


def test_open_mode_resumes_same_student(open_mode_env, monkeypatch):
    mgr = _mgr(open_mode_env, monkeypatch)
    r1 = mgr.login("open-01", "2021001", student_name="홍길동")
    r2 = mgr.login("open-01", "2021001", student_name="홍길동")
    assert r1.session_id == r2.session_id
    assert r2.is_new is False
