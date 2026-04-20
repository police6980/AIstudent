"""Load a teacher's unit configuration from a YAML file into a UnitConfig."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from src.models.schemas import UnitConfig


class UnitConfigError(ValueError):
    """Raised when a unit config file is invalid."""


def load_unit_config(path: str | Path) -> UnitConfig:
    """Load a unit config YAML from `path` and return a validated UnitConfig.

    Raises `UnitConfigError` with a readable message on parse or validation failure.
    """

    p = Path(path)
    if not p.exists():
        raise UnitConfigError(f"Unit config file not found: {p}")

    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - parse error path
        raise UnitConfigError(f"YAML parse error in {p}: {exc}") from exc

    if not isinstance(raw, dict):
        raise UnitConfigError(f"Top-level of {p} must be a mapping (got {type(raw).__name__}).")

    try:
        return UnitConfig.model_validate(raw)
    except ValidationError as exc:
        raise UnitConfigError(f"Invalid unit config in {p}:\n{exc}") from exc


def find_unit_config_by_code(session_code: str, configs_dir: str | Path) -> UnitConfig:
    """Scan configs_dir for a YAML whose session_code matches `session_code`.

    Returns the first match. Raises UnitConfigError if none found.
    """

    dir_path = Path(configs_dir)
    if not dir_path.is_dir():
        raise UnitConfigError(f"Configs directory not found: {dir_path}")

    for yaml_path in sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml")):
        try:
            cfg = load_unit_config(yaml_path)
        except UnitConfigError:
            continue
        if cfg.session_code == session_code:
            return cfg

    raise UnitConfigError(
        f"No unit config with session_code='{session_code}' found in {dir_path}."
    )
