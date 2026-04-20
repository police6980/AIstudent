"""Run the initial concept-map diagnosis via Claude.

Pipeline:
    1. Compute hierarchy + Novak score (rule-based, no LLM).
    2. Load the `concept_map_diagnosis` diagnostic YAML, assemble its
       prompt with reference materials + rubric + the student's map.
    3. Call Claude (analysis model, default Opus) and parse the JSON reply.
    4. Return an InitialDiagnosis dataclass combining both layers.

This feeds the first AI turn in the dialogue (the AI uses
`recommended_first_question` to open the conversation in a way that's
tailored to what the student already put on the map).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from src.config.settings import Settings, get_settings
from src.models.concept_map import ConceptMap, ConceptMapScore
from src.models.schemas import UnitConfig
from src.services.claude_service import ClaudeServiceError
from src.services.concept_maps.novak_scoring import (
    HierarchyResult,
    compute_hierarchy,
    score_concept_map,
)
from src.services.diagnostics import assemble_prompt, load_diagnostic

logger = logging.getLogger(__name__)

DIAGNOSTIC_FILENAME = "concept_map_diagnosis.yaml"


@dataclass
class InitialDiagnosis:
    level: str
    level_justification: str
    detected_misconceptions: list[dict] = field(default_factory=list)
    missing_core_concepts: list[str] = field(default_factory=list)
    strong_points: list[str] = field(default_factory=list)
    zpd_targets: list[str] = field(default_factory=list)
    recommended_first_question: str = ""
    novak_score: Optional[ConceptMapScore] = None
    hierarchy: Optional[HierarchyResult] = None
    raw_claude_output: str = ""

    def to_json(self) -> dict:
        """Serialise to a JSON-safe dict for DB storage."""

        score_dict = self.novak_score.model_dump() if self.novak_score else None
        hierarchy_dict = (
            {
                "concept_levels": self.hierarchy.concept_levels,
                "roots": self.hierarchy.roots,
                "max_level": self.hierarchy.max_level,
                "isolated_concepts": self.hierarchy.isolated_concepts,
                "cycles_present": self.hierarchy.cycles_present,
            }
            if self.hierarchy
            else None
        )
        return {
            "level": self.level,
            "level_justification": self.level_justification,
            "detected_misconceptions": self.detected_misconceptions,
            "missing_core_concepts": self.missing_core_concepts,
            "strong_points": self.strong_points,
            "zpd_targets": self.zpd_targets,
            "recommended_first_question": self.recommended_first_question,
            "novak_score": score_dict,
            "hierarchy": hierarchy_dict,
            "raw_claude_output": self.raw_claude_output,
        }


def _claude_messages_call(
    settings: Settings, system_prompt: str, user_prompt: str, client=None
) -> str:
    """Direct Claude call (bypasses ClaudeService because we need one-shot user msg)."""

    if client is None:
        if not settings.anthropic_api_key:
            raise ClaudeServiceError(
                "ANTHROPIC_API_KEY is not set. Cannot run concept-map diagnosis."
            )
        try:
            import anthropic  # lazy import
        except ImportError as exc:  # pragma: no cover
            raise ClaudeServiceError(
                "anthropic SDK not installed. Run `pip install -r requirements.txt`."
            ) from exc
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Opus 4.7 rejects `temperature`. Older models accept it. Try with, then retry without.
    kwargs = {
        "model": settings.claude_analysis_model,
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    try:
        response = client.messages.create(temperature=0.2, **kwargs)
    except Exception as exc:
        msg = str(exc).lower()
        if "temperature" in msg and ("deprecated" in msg or "not" in msg):
            logger.info("Retrying analysis call without temperature (model rejects it).")
            try:
                response = client.messages.create(**kwargs)
            except Exception as exc2:
                logger.exception("Claude analysis call failed on retry")
                raise ClaudeServiceError(f"Claude analysis call failed: {exc2}") from exc2
        else:
            logger.exception("Claude analysis call failed")
            raise ClaudeServiceError(f"Claude analysis call failed: {exc}") from exc

    chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "".join(chunks).strip()


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from Claude's reply. Tolerates prose around it."""

    if not text:
        raise ValueError("empty response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError("No JSON object found in Claude output.")
    return json.loads(match.group(0))


def _format_propositions(concept_map: ConceptMap) -> list[str]:
    out = []
    for p in concept_map.propositions:
        out.append(
            f"{concept_map.label_for(p.from_id)} —[{p.linking_phrase}]→ "
            f"{concept_map.label_for(p.to_id)}"
        )
    return out


def _format_cross_links(concept_map: ConceptMap) -> list[str]:
    out = []
    for cl in concept_map.cross_links:
        out.append(
            f"{concept_map.label_for(cl.from_id)} ⇢[{cl.linking_phrase}]⇢ "
            f"{concept_map.label_for(cl.to_id)}"
        )
    return out


def _format_examples(concept_map: ConceptMap) -> list[str]:
    return [f"{concept_map.label_for(ex.concept_id)}: {ex.text}" for ex in concept_map.examples]


def diagnose_initial_concept_map(
    concept_map: ConceptMap,
    unit_config: UnitConfig,
    *,
    claude_client=None,
    settings: Settings | None = None,
) -> InitialDiagnosis:
    """Run the full initial-diagnosis pipeline on a student's pre-map.

    `claude_client` is injectable for tests (any object with a
    `messages.create(...)` method compatible with the anthropic SDK).
    """

    settings = settings or get_settings()
    diagnostic = load_diagnostic(DIAGNOSTIC_FILENAME)

    hierarchy = compute_hierarchy(concept_map)
    # Score is computed without misconception info first; LLM will tell us that.
    base_score = score_concept_map(
        concept_map,
        hierarchy=hierarchy,
        weights=diagnostic.extras.get("scoring_weights"),
    )

    variables = {
        "unit_name": unit_config.unit_name,
        "learning_goals": unit_config.learning_goals,
        "common_misconceptions": unit_config.common_misconceptions,
        "concepts": [c.label for c in concept_map.concepts],
        "concept_count": len(concept_map.concepts),
        "propositions": _format_propositions(concept_map),
        "proposition_count": len(concept_map.propositions),
        "cross_links": _format_cross_links(concept_map),
        "cross_link_count": len(concept_map.cross_links),
        "examples": _format_examples(concept_map),
        "example_count": len(concept_map.examples),
        "max_hierarchy_level": hierarchy.max_level,
        "isolated_concepts": [concept_map.label_for(cid) for cid in hierarchy.isolated_concepts],
    }
    user_prompt = assemble_prompt(diagnostic, variables)
    system_prompt = (
        "당신은 과학교육 연구의 질적 분석에 익숙한 AI입니다. "
        "반드시 지정된 JSON 스키마만 출력하세요."
    )

    raw = _claude_messages_call(settings, system_prompt, user_prompt, client=claude_client)

    try:
        parsed = _extract_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Concept map diagnosis JSON parse failed: %s", exc)
        # Graceful fallback — surface the raw output so the instructor can inspect.
        return InitialDiagnosis(
            level="unknown",
            level_justification=f"(JSON 파싱 실패: {exc})",
            recommended_first_question="오늘 배운 걸 네 말로 어디서부터 설명해볼까?",
            novak_score=base_score,
            hierarchy=hierarchy,
            raw_claude_output=raw,
        )

    misconceptions = parsed.get("detected_misconceptions") or []
    # Re-score with misconception count so the final Novak score reflects what
    # the LLM diagnosed.
    final_score = score_concept_map(
        concept_map,
        hierarchy=hierarchy,
        weights=diagnostic.extras.get("scoring_weights"),
        misconception_count=len(misconceptions),
    )

    return InitialDiagnosis(
        level=str(parsed.get("level", "unknown")),
        level_justification=str(parsed.get("level_justification", "")),
        detected_misconceptions=list(misconceptions) if isinstance(misconceptions, list) else [],
        missing_core_concepts=list(parsed.get("missing_core_concepts", []) or []),
        strong_points=list(parsed.get("strong_points", []) or []),
        zpd_targets=list(parsed.get("zpd_targets", []) or []),
        recommended_first_question=str(parsed.get("recommended_first_question", "")),
        novak_score=final_score,
        hierarchy=hierarchy,
        raw_claude_output=raw,
    )
