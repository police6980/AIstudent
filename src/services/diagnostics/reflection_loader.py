"""Load and save the reflection questions configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

DEFAULT_REFLECTION_PATH = Path("configs/reflection_questions.yaml")


class ReflectionQuestionsError(ValueError):
    """Raised when the reflection questions YAML is invalid."""


@dataclass
class ReflectionQuestion:
    id: str
    title: str
    prompt: str
    min_chars: int = 100

    def validate_answer(self, text: str) -> tuple[bool, int]:
        """Return (is_valid, char_count). Whitespace stripped before counting."""

        stripped = (text or "").strip()
        count = len(stripped)
        return count >= self.min_chars, count


def load_reflection_questions(
    path: str | Path = DEFAULT_REFLECTION_PATH,
) -> list[ReflectionQuestion]:
    """Load reflection questions from YAML. Raises on any structural problem."""

    p = Path(path)
    if not p.exists():
        raise ReflectionQuestionsError(f"Reflection questions file not found: {p}")

    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ReflectionQuestionsError(f"YAML parse error in {p}: {exc}") from exc

    if not isinstance(raw, dict) or "questions" not in raw:
        raise ReflectionQuestionsError(
            f"{p} must contain a top-level 'questions' list."
        )
    items = raw["questions"]
    if not isinstance(items, list) or not items:
        raise ReflectionQuestionsError(f"{p}: 'questions' must be a non-empty list.")

    questions: list[ReflectionQuestion] = []
    seen_ids: set[str] = set()
    for idx, q in enumerate(items):
        if not isinstance(q, dict):
            raise ReflectionQuestionsError(f"{p}: question {idx} must be a mapping.")
        for key in ("id", "title", "prompt"):
            if key not in q:
                raise ReflectionQuestionsError(f"{p}: question {idx} missing '{key}'.")
        qid = str(q["id"]).strip()
        if qid in seen_ids:
            raise ReflectionQuestionsError(f"{p}: duplicate question id '{qid}'.")
        seen_ids.add(qid)
        questions.append(
            ReflectionQuestion(
                id=qid,
                title=str(q["title"]).strip(),
                prompt=str(q["prompt"]).strip(),
                min_chars=int(q.get("min_chars", 100)),
            )
        )
    return questions


def save_reflection_questions(
    questions: list[ReflectionQuestion],
    path: str | Path = DEFAULT_REFLECTION_PATH,
) -> None:
    """Serialise questions back to YAML. Used by the instructor UI."""

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"questions": [asdict(q) for q in questions]}
    p.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
