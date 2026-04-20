"""Assemble the final LLM prompt for a diagnostic call.

The prompt_template in each diagnostic YAML contains `{placeholder}` slots.
This module substitutes the reference-materials block and any other
runtime-provided placeholders safely (missing keys do not crash).
"""

from __future__ import annotations

from typing import Any

from src.services.diagnostics.diagnostic_config import DiagnosticConfig
from src.services.diagnostics.reference_loader import (
    format_materials_block,
    load_reference_materials,
)


class _SafeDict(dict):
    """Dict that returns '{key}' for missing keys during str.format_map.

    This keeps prompt templates resilient when a caller forgets to supply
    an optional variable — the token stays as a visible placeholder instead
    of raising KeyError mid-formatting.
    """

    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return "{" + key + "}"


def _format_for_prompt(value: Any) -> str:
    """Render arbitrary Python values as readable prompt text."""

    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    if isinstance(value, list):
        if all(isinstance(x, str) for x in value):
            return "\n".join(f"- {x}" for x in value) if value else "(없음)"
        import json

        return json.dumps(value, ensure_ascii=False, indent=2)
    if isinstance(value, dict):
        import json

        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def assemble_prompt(
    diagnostic: DiagnosticConfig,
    variables: dict[str, Any],
    *,
    ref_dir=None,
) -> str:
    """Fill the diagnostic's prompt_template with runtime variables + references.

    The placeholder `{reference_materials}` is always populated from
    `diagnostic.reference_materials` (via reference_loader). Caller-provided
    `variables` fill every other `{...}` slot.
    """

    # Load reference materials and pre-format to a single block.
    kwargs = {"load_reference_materials": load_reference_materials}  # satisfy lint
    del kwargs
    if ref_dir is None:
        materials = load_reference_materials(diagnostic.reference_materials)
    else:
        materials = load_reference_materials(diagnostic.reference_materials, ref_dir=ref_dir)
    references_block = format_materials_block(materials)

    # Also expose nested structured extras (rubric, weights, etc.) so templates
    # can reference them by key (e.g. `{level_rubric}` reads extras['level_rubric']).
    auto_vars: dict[str, Any] = {"reference_materials": references_block}
    for k, v in diagnostic.extras.items():
        if k not in variables and k != "reference_materials":
            auto_vars[k] = v

    combined = {**auto_vars, **variables}
    formatted = {k: _format_for_prompt(v) for k, v in combined.items()}

    return diagnostic.prompt_template.format_map(_SafeDict(formatted))
