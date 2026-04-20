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


class SessionStep(str, Enum):
    """Granular step within an in_progress session.

    Flow: PRE_MAP → DIALOGUE → POST_MAP → REFLECTION → COMPLETED
    """

    PRE_MAP = "pre_map"          # student is building the initial concept map
    DIALOGUE = "dialogue"        # concept map submitted, chatting with AI
    POST_MAP = "post_map"        # chat ended, student building the post-map
    REFLECTION = "reflection"    # post-map submitted, answering 5 questions
    COMPLETED = "completed"      # everything done; PDF available (Phase B5)

    @classmethod
    def order(cls) -> list["SessionStep"]:
        return [cls.PRE_MAP, cls.DIALOGUE, cls.POST_MAP, cls.REFLECTION, cls.COMPLETED]

    def is_before(self, other: "SessionStep") -> bool:
        seq = self.order()
        return seq.index(self) < seq.index(other)
