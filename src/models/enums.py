"""Enums for hint types, session states, and speaker roles."""

from enum import Enum


class HintType(str, Enum):
    """Six scaffolding hint types (Vygotsky-aligned). Used from Milestone B+."""

    SOCRATIC = "socratic"
    BRIDGING = "bridging"
    COUNTEREXAMPLE = "counterexample"
    EVIDENCE = "evidence"
    REPRESENTATION = "representation"
    METACOGNITIVE = "metacognitive"


class Speaker(str, Enum):
    """Who produced a given turn."""

    STUDENT = "student"   # preservice teacher (the explainer)
    AI = "ai"             # peer-learner persona with misconceptions


class SessionStatus(str, Enum):
    """Lifecycle of a session."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
