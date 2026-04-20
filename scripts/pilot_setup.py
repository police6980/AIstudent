"""Interactive pilot-setup wizard for the instructor.

Asks a few questions, creates a unit YAML, generates N student accounts,
and prints the distribution-ready accounts file path. Designed so an
instructor without Python experience can prepare a pilot in <5 minutes.

Run:
    source .venv/bin/activate
    python scripts/pilot_setup.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

CONFIGS_DIR = Path("configs")
EXAMPLE_YAML = CONFIGS_DIR / "example_photosynthesis.yaml"


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw or default


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = _ask(prompt, str(default))
        try:
            return int(raw)
        except ValueError:
            print("  숫자로 입력하세요.")


def main() -> int:
    print("=" * 64)
    print("  📚 예비교사 과학 설명 훈련 — 파일럿 셋업")
    print("=" * 64)
    print()
    print("단원 하나를 만들고 학생 계정을 생성합니다. (수정은 나중에")
    print("관리자 페이지 /?admin=true 에서도 가능해요.)")
    print()

    if not EXAMPLE_YAML.exists():
        print(f"❌ 예시 YAML이 없어요: {EXAMPLE_YAML}")
        return 2

    example = yaml.safe_load(EXAMPLE_YAML.read_text(encoding="utf-8"))

    print("─" * 64)
    unit_code = _ask("단원 코드 (URL 에 들어갈 이름)", "photo-01")
    unit_name = _ask("단원명", "광합성")
    target_grade = _ask("대상 학년(가르칠 대상)", "초등 6학년")
    persona_name = _ask("AI 페르소나 이름 (또래 대학생)", "지후")
    instructor_name = _ask("담당 교수 이름", "교수")
    count = _ask_int("학생 계정 수", 30)
    print("─" * 64)

    # Start from example template, swap the fields the instructor set.
    config = dict(example)
    config["unit_code"] = unit_code
    config["unit_name"] = unit_name
    config["target_grade_for_teaching"] = target_grade
    config["persona_name"] = persona_name
    config["instructor_name"] = instructor_name
    config["student_accounts"] = []  # will be filled by generate_codes

    out_yaml = CONFIGS_DIR / f"{unit_code}.yaml"
    if out_yaml.exists():
        overwrite = _ask(f"⚠️ {out_yaml} 이미 존재해요. 덮어쓸까요? (y/N)", "N")
        if overwrite.lower() != "y":
            print("중단.")
            return 1

    out_yaml.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"✅ 단원 YAML 저장: {out_yaml}")

    # Generate accounts
    from src.tools.generate_codes import run as gen_codes_run

    rc = gen_codes_run(out_yaml, count=count, force=True)
    if rc != 0:
        print("❌ 학생 계정 생성 실패.")
        return rc

    accounts_txt = out_yaml.with_suffix(".accounts.txt")
    print()
    print("=" * 64)
    print("  🎯 파일럿 준비 끝")
    print("=" * 64)
    print(f"  단원 YAML    : {out_yaml}")
    print(f"  학생 배포용  : {accounts_txt}")
    print()
    print("다음 단계:")
    print("  1. .env 에 ANTHROPIC_API_KEY 가 채워져 있는지 확인")
    print("  2. 앱 실행:")
    print("     python -m src.main --share")
    print("     (콘솔에 'Public URL: https://xxxx.gradio.live' 출력됨)")
    print(f"  3. 학생에게 '<Public URL>/?unit={unit_code}' + 개별 ID/PW 배포")
    print(f"     ({accounts_txt} 내용을 학생 수 만큼 나눠서 전달)")
    print()
    print(f"  관리자 페이지: <Public URL>/?admin=true")
    print(f"  관리자 비밀번호는 .env 의 INSTRUCTOR_PASSWORD 값.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
