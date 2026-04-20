"""Interactive pilot-setup wizard for the instructor.

Asks a few questions, creates a unit YAML, generates N student accounts,
and prints the distribution-ready accounts file path.
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
            print("  Please enter a number.")


def main() -> int:
    print("=" * 64)
    print("  Preservice Teacher Training  -  Pilot Setup")
    print("=" * 64)
    print()
    print("Creates a unit and N student accounts.")
    print("(You can also edit later from the admin page /?admin=true.)")
    print()

    if not EXAMPLE_YAML.exists():
        print(f"[X] Example YAML not found: {EXAMPLE_YAML}", file=sys.stderr)
        return 2

    example = yaml.safe_load(EXAMPLE_YAML.read_text(encoding="utf-8"))

    print("-" * 64)
    unit_code = _ask("Unit code (used in URL, e.g. photo-01)", "photo-01")
    unit_name = _ask("Unit name (Korean OK)", "광합성")
    target_grade = _ask("Target grade to teach", "초등 6학년")
    persona_name = _ask("AI peer name", "지후")
    instructor_name = _ask("Instructor name", "교수")
    count = _ask_int("Number of student accounts", 30)
    print("-" * 64)

    config = dict(example)
    config["unit_code"] = unit_code
    config["unit_name"] = unit_name
    config["target_grade_for_teaching"] = target_grade
    config["persona_name"] = persona_name
    config["instructor_name"] = instructor_name
    config["student_accounts"] = []

    out_yaml = CONFIGS_DIR / f"{unit_code}.yaml"
    if out_yaml.exists():
        overwrite = _ask(f"[!] {out_yaml} already exists. Overwrite? (y/N)", "N")
        if overwrite.lower() != "y":
            print("Aborted.")
            return 1

    out_yaml.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"[OK] Unit YAML saved: {out_yaml}")

    from src.tools.generate_codes import run as gen_codes_run

    rc = gen_codes_run(out_yaml, count=count, force=True)
    if rc != 0:
        print("[X] Failed to generate student accounts.")
        return rc

    accounts_txt = out_yaml.with_suffix(".accounts.txt")
    print()
    print("=" * 64)
    print("  [OK] Pilot is ready")
    print("=" * 64)
    print(f"  Unit YAML      : {out_yaml}")
    print(f"  Accounts file  : {accounts_txt}")
    print()
    print("Next steps:")
    print("  1. Make sure ANTHROPIC_API_KEY is set in .env")
    print("  2. Run the app:")
    print("     python -m src.main --share")
    print("     (A 'Public URL: https://xxxx.gradio.live' line will appear)")
    print(f"  3. Send students the link + IDs:  <Public URL>/?unit={unit_code}")
    print(f"     (open {accounts_txt} and send each student one line)")
    print()
    print("  Admin page:   <Public URL>/?admin=true")
    print("  Admin password is the INSTRUCTOR_PASSWORD value in .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
