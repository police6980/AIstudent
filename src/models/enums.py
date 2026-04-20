"""Enums for grade levels, hint types, and speaker roles."""

from enum import Enum


class GradeLevel(str, Enum):
    """School stage for Vygotsky scaffolding variation."""

    ELEMENTARY = "elementary"
    MIDDLE = "middle"
    HIGH = "high"
    SCIENCE_HIGH = "science_high"


class HintType(str, Enum):
    """Six scaffolding hint types (Vygotsky-aligned)."""

    SOCRATIC = "socratic"
    BRIDGING = "bridging"
    COUNTEREXAMPLE = "counterexample"
    EVIDENCE = "evidence"
    REPRESENTATION = "representation"
    METACOGNITIVE = "metacognitive"


class Speaker(str, Enum):
    """Who produced a given turn."""

    STUDENT = "student"
    AI = "ai"
