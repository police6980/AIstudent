"""Layer 2: school-stage-specific scaffolding variations (Korean)."""

from src.models.enums import GradeLevel
from src.prompts.layer2_grade.elementary import ELEMENTARY_LAYER
from src.prompts.layer2_grade.high import HIGH_LAYER
from src.prompts.layer2_grade.middle import MIDDLE_LAYER
from src.prompts.layer2_grade.science_high import SCIENCE_HIGH_LAYER

_GRADE_PROMPTS: dict[GradeLevel, str] = {
    GradeLevel.ELEMENTARY: ELEMENTARY_LAYER,
    GradeLevel.MIDDLE: MIDDLE_LAYER,
    GradeLevel.HIGH: HIGH_LAYER,
    GradeLevel.SCIENCE_HIGH: SCIENCE_HIGH_LAYER,
}


def get_grade_layer_prompt(grade: GradeLevel) -> str:
    """Return the Layer 2 prompt string for the given grade level."""

    try:
        return _GRADE_PROMPTS[grade]
    except KeyError as exc:  # pragma: no cover - enum coverage
        raise ValueError(f"Unsupported grade level: {grade!r}") from exc


__all__ = ["get_grade_layer_prompt"]
