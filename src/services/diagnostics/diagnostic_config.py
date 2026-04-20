"""Load and validate diagnostic YAMLs from configs/diagnostics/."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_DIAG_DIR = Path("configs/diagnostics")


class DiagnosticConfigError(ValueError):
    """Raised when a diagnostic YAML is invalid or missing."""


@dataclass
class DiagnosticConfig:
    """In-memory representation of one diagnostic module's config."""

    filename: str
    name: str
    description: str
    reference_materials: list[str] = field(default_factory=list)
    prompt_template: str = ""
    # Free-form extra fields (scoring_weights, rubric, pck_dimensions, etc.) —
    # we keep them as a generic dict so each diagnostic can define its own.
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Return the diagnostic's identifier (filename without extension)."""

        return Path(self.filename).stem


def _coerce(raw: dict[str, Any], filename: str) -> DiagnosticConfig:
    required = ["name", "prompt_template"]
    missing = [k for k in required if k not in raw]
    if missing:
        raise DiagnosticConfigError(
            f"Diagnostic '{filename}' missing required field(s): {', '.join(missing)}"
        )

    reserved = {"name", "description", "reference_materials", "prompt_template"}
    extras = {k: v for k, v in raw.items() if k not in reserved}

    refs = raw.get("reference_materials") or []
    if not isinstance(refs, list) or not all(isinstance(x, str) for x in refs):
        raise DiagnosticConfigError(
            f"Diagnostic '{filename}': 'reference_materials' must be a list of filenames."
        )

    return DiagnosticConfig(
        filename=filename,
        name=str(raw["name"]),
        description=str(raw.get("description", "")),
        reference_materials=refs,
        prompt_template=str(raw["prompt_template"]),
        extras=extras,
    )


def load_diagnostic(filename: str, diag_dir: Path = DEFAULT_DIAG_DIR) -> DiagnosticConfig:
    """Load a single diagnostic config by filename."""

    path = Path(diag_dir) / filename
    if not path.exists():
        raise DiagnosticConfigError(f"Diagnostic config not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DiagnosticConfigError(f"YAML parse error in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise DiagnosticConfigError(
            f"Top-level of {path} must be a mapping, got {type(raw).__name__}."
        )
    return _coerce(raw, filename)


def list_diagnostics(diag_dir: Path = DEFAULT_DIAG_DIR) -> list[str]:
    """Return filenames of all diagnostic YAMLs present in diag_dir."""

    dir_path = Path(diag_dir)
    if not dir_path.is_dir():
        return []
    return sorted(
        p.name for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in {".yaml", ".yml"}
    )


def save_diagnostic(
    filename: str,
    fields: dict[str, Any],
    diag_dir: Path = DEFAULT_DIAG_DIR,
) -> None:
    """Write a diagnostic YAML. Used by the instructor UI."""

    dir_path = Path(diag_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / filename
    path.write_text(
        yaml.safe_dump(fields, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
