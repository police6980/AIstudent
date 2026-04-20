"""Pydantic schemas for Novak-style concept maps.

Concept map structure follows Novak's 5 elements:
    - concepts (nodes)
    - propositions (concept —[linking phrase]→ concept): basic unit of meaning
    - cross_links: propositions that bridge different branches (integrative)
    - examples: specific instances anchored to a concept
Hierarchy is computed automatically from graph structure (see novak_scoring.py).
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _normalize_label(label: str) -> str:
    """Collapse inner whitespace, strip edges. Concept labels are matched exactly."""

    return re.sub(r"\s+", " ", (label or "")).strip()


class Concept(BaseModel):
    """A single node in the concept map."""

    id: str                     # local id within the map, e.g. "c1"
    label: str                  # human-readable concept name

    @field_validator("label")
    @classmethod
    def _clean_label(cls, v: str) -> str:
        v = _normalize_label(v)
        if not v:
            raise ValueError("Concept label cannot be empty.")
        return v


class Proposition(BaseModel):
    """A concept-concept relation of the form: from —[linking]→ to."""

    from_id: str
    to_id: str
    linking_phrase: str

    @field_validator("linking_phrase")
    @classmethod
    def _clean_linking(cls, v: str) -> str:
        v = _normalize_label(v)
        if not v:
            raise ValueError("Linking phrase cannot be empty.")
        return v


class CrossLink(BaseModel):
    """A proposition that the student explicitly marks as a cross-branch link.

    Structurally identical to a Proposition but scored differently (Novak: +10).
    """

    from_id: str
    to_id: str
    linking_phrase: str

    @field_validator("linking_phrase")
    @classmethod
    def _clean_linking(cls, v: str) -> str:
        v = _normalize_label(v)
        if not v:
            raise ValueError("Linking phrase cannot be empty.")
        return v


class Example(BaseModel):
    """A specific example attached to a concept."""

    concept_id: str
    text: str

    @field_validator("text")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        v = _normalize_label(v)
        if not v:
            raise ValueError("Example text cannot be empty.")
        return v


class ConceptMap(BaseModel):
    """Full Novak-style concept map submitted by a student."""

    concepts: list[Concept] = Field(default_factory=list)
    propositions: list[Proposition] = Field(default_factory=list)
    cross_links: list[CrossLink] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)

    def validate_references(self) -> list[str]:
        """Return a list of human-readable issues with internal references.

        Non-raising: the UI may want to warn but still accept imperfect maps.
        """

        problems: list[str] = []
        ids = {c.id for c in self.concepts}
        labels_seen: dict[str, str] = {}

        # Duplicate concept ids
        seen_ids: set[str] = set()
        for c in self.concepts:
            if c.id in seen_ids:
                problems.append(f"중복 concept id: '{c.id}'")
            seen_ids.add(c.id)

        # Duplicate concept labels (case-insensitive) — not fatal but surface it
        for c in self.concepts:
            low = c.label.casefold()
            if low in labels_seen and labels_seen[low] != c.id:
                problems.append(
                    f"중복 개념 이름: '{c.label}' (id '{c.id}' 와 '{labels_seen[low]}' 동시)"
                )
            labels_seen.setdefault(low, c.id)

        # Reference checks
        for i, p in enumerate(self.propositions):
            if p.from_id not in ids:
                problems.append(f"명제 {i}: 알 수 없는 from_id '{p.from_id}'")
            if p.to_id not in ids:
                problems.append(f"명제 {i}: 알 수 없는 to_id '{p.to_id}'")
            if p.from_id == p.to_id:
                problems.append(f"명제 {i}: from 과 to 가 같아요 ('{p.from_id}')")

        for i, cl in enumerate(self.cross_links):
            if cl.from_id not in ids:
                problems.append(f"교차연결 {i}: 알 수 없는 from_id '{cl.from_id}'")
            if cl.to_id not in ids:
                problems.append(f"교차연결 {i}: 알 수 없는 to_id '{cl.to_id}'")
            if cl.from_id == cl.to_id:
                problems.append(f"교차연결 {i}: from 과 to 가 같아요 ('{cl.from_id}')")

        for i, ex in enumerate(self.examples):
            if ex.concept_id not in ids:
                problems.append(f"예시 {i}: 알 수 없는 concept_id '{ex.concept_id}'")

        return problems

    def concept_by_id(self, cid: str) -> Optional[Concept]:
        for c in self.concepts:
            if c.id == cid:
                return c
        return None

    def label_for(self, cid: str) -> str:
        c = self.concept_by_id(cid)
        return c.label if c else cid


class ConceptMapScore(BaseModel):
    """Novak-style score breakdown for a concept map."""

    proposition_count: int
    valid_proposition_count: int
    max_hierarchy_level: int  # number of distinct depth levels found
    cross_link_count: int
    example_count: int
    isolated_concept_count: int
    total: float
    # Weights used (so report can show which configuration was applied)
    weights_used: dict = Field(default_factory=dict)
