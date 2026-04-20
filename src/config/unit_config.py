"""Load instructor unit configurations from YAML, look them up by unit_code."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from src.models.schemas import UnitConfig


class UnitConfigError(ValueError):
    """Raised when a unit config file is invalid."""


def load_unit_config(path: str | Path) -> UnitConfig:
    """Load and validate a unit YAML into a UnitConfig.

    Raises `UnitConfigError` with a readable message on parse or schema failure.
    """

    p = Path(path)
    if not p.exists():
        raise UnitConfigError(f"Unit config file not found: {p}")

    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover
        raise UnitConfigError(f"YAML parse error in {p}: {exc}") from exc

    if not isinstance(raw, dict):
        raise UnitConfigError(f"Top-level of {p} must be a mapping (got {type(raw).__name__}).")

    try:
        return UnitConfig.model_validate(raw)
    except ValidationError as exc:
        raise UnitConfigError(f"Invalid unit config in {p}:\n{exc}") from exc


def find_unit_config_by_code(unit_code: str, configs_dir: str | Path) -> UnitConfig:
    """Scan `configs_dir` for a YAML whose unit_code matches.

    Raises UnitConfigError if none found.
    """

    dir_path = Path(configs_dir)
    if not dir_path.is_dir():
        raise UnitConfigError(f"Configs directory not found: {dir_path}")

    for yaml_path in sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml")):
        try:
            cfg = load_unit_config(yaml_path)
        except UnitConfigError:
            continue
        if cfg.unit_code == unit_code:
            return cfg

    raise UnitConfigError(f"No unit config with unit_code='{unit_code}' found in {dir_path}.")


def list_all_unit_codes(configs_dir: str | Path) -> list[str]:
    """Return unit_codes of every valid YAML in configs_dir (for debugging/UI)."""

    dir_path = Path(configs_dir)
    if not dir_path.is_dir():
        return []
    codes: list[str] = []
    for yaml_path in sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml")):
        try:
            cfg = load_unit_config(yaml_path)
        except UnitConfigError:
            continue
        codes.append(cfg.unit_code)
    return codes


def authenticate(unit_config: UnitConfig, student_id: str, password: str) -> bool:
    """Return True iff (student_id, password) matches one account in the unit."""

    sid = (student_id or "").strip()
    pw = (password or "").strip()
    if not sid or not pw:
        return False
    for acc in unit_config.student_accounts:
        if acc.id == sid and acc.password == pw:
            return True
    return False
