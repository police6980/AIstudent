"""Tests for the student-account generator CLI."""

from __future__ import annotations

import yaml

from src.tools.generate_codes import (
    PASSWORD_ALPHABET,
    PASSWORD_LENGTH,
    make_accounts,
    make_password,
    run,
)


def test_make_password_length_and_alphabet():
    for _ in range(50):
        pw = make_password()
        assert len(pw) == PASSWORD_LENGTH
        assert all(ch in PASSWORD_ALPHABET for ch in pw)


def test_password_alphabet_excludes_ambiguous():
    # Must not contain confusing characters.
    for ch in ["0", "o", "O", "1", "l", "I", "i"]:
        assert ch not in PASSWORD_ALPHABET


def test_make_accounts_ids_sequential_and_padded():
    accounts = make_accounts(30)
    assert len(accounts) == 30
    assert accounts[0]["id"] == "s01"
    assert accounts[29]["id"] == "s30"
    # Passwords should (almost certainly) all be unique.
    passwords = [a["password"] for a in accounts]
    assert len(set(passwords)) == len(passwords)


def test_run_writes_accounts_and_sidecar(tmp_path):
    yaml_path = tmp_path / "test-unit.yaml"
    yaml_path.write_text(
        "unit_code: test-unit\n"
        "subject: science\n"
        "unit_name: 테스트\n"
        "learning_goals: []\n"
        "rubric_items: []\n"
        "persona_name: 지후\n"
        "instructor_name: 김교수\n",
        encoding="utf-8",
    )

    rc = run(yaml_path, count=5, force=False)
    assert rc == 0

    updated = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert len(updated["student_accounts"]) == 5
    assert updated["student_accounts"][0]["id"] == "s01"

    sidecar = yaml_path.with_suffix(".accounts.txt")
    assert sidecar.exists()
    txt = sidecar.read_text(encoding="utf-8")
    assert "s01" in txt
    assert "s05" in txt
    assert "비밀번호" in txt


def test_run_refuses_overwrite_without_force(tmp_path):
    yaml_path = tmp_path / "test-unit.yaml"
    yaml_path.write_text(
        "unit_code: test-unit\n"
        "subject: science\n"
        "unit_name: 테스트\n"
        "learning_goals: []\n"
        "rubric_items: []\n"
        "persona_name: 지후\n"
        "instructor_name: 김교수\n"
        "student_accounts:\n"
        "  - id: s01\n"
        "    password: abcde\n",
        encoding="utf-8",
    )
    rc = run(yaml_path, count=5, force=False)
    assert rc == 1  # refused
    # Original single account preserved.
    updated = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert len(updated["student_accounts"]) == 1


def test_run_force_overwrites(tmp_path):
    yaml_path = tmp_path / "test-unit.yaml"
    yaml_path.write_text(
        "unit_code: test-unit\n"
        "subject: science\n"
        "unit_name: 테스트\n"
        "learning_goals: []\n"
        "rubric_items: []\n"
        "persona_name: 지후\n"
        "instructor_name: 김교수\n"
        "student_accounts:\n"
        "  - id: s01\n"
        "    password: abcde\n",
        encoding="utf-8",
    )
    rc = run(yaml_path, count=3, force=True)
    assert rc == 0
    updated = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert len(updated["student_accounts"]) == 3
