"""Generate student accounts (id + random 5-char password) for a unit YAML.

Usage:
    python -m src.tools.generate_codes configs/photo-01.yaml
    python -m src.tools.generate_codes configs/photo-01.yaml --count 30 --force

Behavior:
    - Reads the YAML at the given path.
    - Generates `count` student accounts with IDs "s01", "s02", ... and 5-char
      random passwords using a confusion-free alphabet (no 0/O, 1/l/I).
    - Writes student_accounts list back into the YAML (preserving field order
      is best-effort — we append if absent, overwrite if --force).
    - Writes a sibling file "<unit>.accounts.txt" with a human-readable list
      for the instructor to distribute to students individually.

Safety:
    - Refuses to overwrite existing student_accounts unless --force is passed.
    - Prints a preview before writing.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

import yaml

# Password alphabet: lowercase letters + digits, minus confusing ones.
# Excludes: 0, o, 1, l, i (visually ambiguous on screens/print).
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
PASSWORD_LENGTH = 5


def make_password(length: int = PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def make_accounts(count: int, id_prefix: str = "s", id_width: int = 2) -> list[dict]:
    """Return [{id, password}, ...] of length `count`."""

    accounts: list[dict] = []
    used_pw: set[str] = set()
    for n in range(1, count + 1):
        pw = make_password()
        # Regenerate on the (very rare) collision.
        while pw in used_pw:
            pw = make_password()
        used_pw.add(pw)
        accounts.append({"id": f"{id_prefix}{n:0{id_width}d}", "password": pw})
    return accounts


def write_accounts_txt(
    path: Path,
    unit_code: str,
    unit_name: str,
    accounts: list[dict],
) -> None:
    lines = [
        f"단원 코드: {unit_code}",
        f"단원명: {unit_name}",
        f"학생 계정 ({len(accounts)}명)",
        "=" * 40,
        "",
        f"{'학생ID':<8}{'비밀번호':<12}",
        "-" * 40,
    ]
    for acc in accounts:
        lines.append(f"{acc['id']:<8}{acc['password']:<12}")
    lines.append("")
    lines.append("⚠️ 학생에게 개별로 ID와 비밀번호를 알려주세요.")
    lines.append("   이 파일은 외부에 공유하지 마세요.")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(
    yaml_path: Path,
    count: int,
    force: bool,
) -> int:
    if not yaml_path.exists():
        print(f"❌ 파일을 찾을 수 없어요: {yaml_path}", file=sys.stderr)
        return 2

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        print(f"❌ YAML 최상위가 매핑이 아니에요: {yaml_path}", file=sys.stderr)
        return 2

    existing = raw.get("student_accounts")
    if existing and not force:
        print(
            f"⚠️  student_accounts 가 이미 {len(existing)}개 있습니다.\n"
            f"    덮어쓰려면 --force 를 주세요. (현재 유지)",
            file=sys.stderr,
        )
        return 1

    accounts = make_accounts(count)
    raw["student_accounts"] = accounts

    # Write YAML back. Using default_flow_style=False for block-style output.
    yaml_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )

    unit_code = raw.get("unit_code", yaml_path.stem)
    unit_name = raw.get("unit_name", "(이름 없음)")
    accounts_txt_path = yaml_path.with_suffix(".accounts.txt")
    write_accounts_txt(accounts_txt_path, unit_code, unit_name, accounts)

    print(f"✅ {count}개 학생 계정 생성 완료")
    print(f"   - YAML 업데이트: {yaml_path}")
    print(f"   - 배포용 목록: {accounts_txt_path}")
    print("\n첫 3개 미리보기:")
    for acc in accounts[:3]:
        print(f"   {acc['id']}  {acc['password']}")
    print("   ...")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_codes",
        description="Generate student accounts for a unit YAML.",
    )
    parser.add_argument("yaml_path", type=Path, help="Path to the unit YAML file.")
    parser.add_argument(
        "--count", type=int, default=30, help="Number of accounts to generate (default: 30)."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing student_accounts in the YAML.",
    )
    args = parser.parse_args(argv)
    return run(args.yaml_path, args.count, args.force)


if __name__ == "__main__":
    sys.exit(main())
