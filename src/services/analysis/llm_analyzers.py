"""LLM-backed analyzers for a completed session.

Each analyzer:
    1. Loads a diagnostic YAML from configs/diagnostics/.
    2. Builds the variable dict the YAML's prompt_template expects.
    3. Calls Claude (analysis model) via assemble_prompt.
    4. Parses JSON output (tolerant to prose wrapping).
    5. Returns a plain dict suitable for session.analysis_json.

Failures are caught and surfaced as {"_error": "..."} so one failing
analyzer does not nuke the whole report.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.config.settings import Settings, get_settings
from src.models.concept_map import ConceptMap
from src.models.enums import Speaker
from src.models.schemas import Turn, UnitConfig
from src.services.claude_service import ClaudeServiceError
from src.services.concept_maps.novak_scoring import (
    compute_hierarchy,
    score_concept_map,
)
from src.services.diagnostics import assemble_prompt, load_diagnostic

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
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


def _claude_call(
    settings: Settings,
    system_prompt: str,
    user_prompt: str,
    *,
    client=None,
    max_tokens: int = 3500,
    temperature: float = 0.2,
) -> str:
    """Direct Claude Messages API call (uses the analysis model)."""

    if client is None:
        if not settings.anthropic_api_key:
            raise ClaudeServiceError(
                "ANTHROPIC_API_KEY is not set. Cannot run analysis."
            )
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise ClaudeServiceError(
                "anthropic SDK not installed. Run `pip install -r requirements.txt`."
            ) from exc
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.create(
            model=settings.claude_analysis_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:
        logger.exception("Claude analysis call failed")
        raise ClaudeServiceError(f"Claude analysis call failed: {exc}") from exc

    chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "".join(chunks).strip()


def _format_transcript(turns: list[Turn]) -> str:
    lines = []
    for i, t in enumerate(turns):
        role = "학생" if t.speaker == Speaker.STUDENT else "AI"
        lines.append(f"[턴 {i}] {role}: {t.content}")
    return "\n".join(lines)


def _format_student_only(turns: list[Turn]) -> str:
    lines = []
    for i, t in enumerate(turns):
        if t.speaker != Speaker.STUDENT:
            continue
        lines.append(f"[턴 {i}] 학생: {t.content}")
    return "\n".join(lines)


def _format_ai_only(turns: list[Turn]) -> str:
    lines = []
    for i, t in enumerate(turns):
        if t.speaker != Speaker.AI:
            continue
        lines.append(f"[턴 {i}] AI: {t.content}")
    return "\n".join(lines)


def _format_concept_map(cmap: ConceptMap) -> dict[str, Any]:
    return {
        "concepts": [c.label for c in cmap.concepts],
        "propositions": [
            f"{cmap.label_for(p.from_id)} —[{p.linking_phrase}]→ {cmap.label_for(p.to_id)}"
            for p in cmap.propositions
        ],
        "cross_links": [
            f"{cmap.label_for(cl.from_id)} ⇢[{cl.linking_phrase}]⇢ {cmap.label_for(cl.to_id)}"
            for cl in cmap.cross_links
        ],
        "examples": [f"{cmap.label_for(ex.concept_id)}: {ex.text}" for ex in cmap.examples],
    }


# ---------- 1) Misconception tracking ----------

def analyse_misconceptions(
    *,
    turns: list[Turn],
    unit_config: UnitConfig,
    initial_student_misconceptions: list[str] | None = None,
    settings: Settings | None = None,
    claude_client=None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    diagnostic = load_diagnostic("misconception_tracking.yaml")
    variables = {
        "unit_name": unit_config.unit_name,
        "learning_goals": unit_config.learning_goals,
        "common_misconceptions": unit_config.common_misconceptions,
        "initial_ai_misconceptions": unit_config.persona_initial_misconceptions,
        "initial_student_misconceptions": initial_student_misconceptions or [],
        "transcript_with_indices": _format_transcript(turns),
    }
    user = assemble_prompt(diagnostic, variables)
    system = "당신은 개념 변화 연구에 능한 과학교육 분석가입니다. 반드시 JSON만 출력하세요."
    try:
        raw = _claude_call(settings, system, user, client=claude_client)
        return _extract_json(raw)
    except (ClaudeServiceError, ValueError, json.JSONDecodeError) as exc:
        logger.error("misconception analysis failed: %s", exc)
        return {"_error": str(exc)}


# ---------- 2) Scaffolding quality ----------

def analyse_scaffolding_quality(
    *,
    turns: list[Turn],
    unit_config: UnitConfig,
    settings: Settings | None = None,
    claude_client=None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    diagnostic = load_diagnostic("scaffolding_quality.yaml")
    # Feed AI turns with small student-turn context windows.
    variables = {
        "ai_turns_with_context": _format_transcript(turns),
    }
    user = assemble_prompt(diagnostic, variables)
    system = "당신은 Vygotsky 비계 이론 분석가입니다. 반드시 JSON만 출력하세요."
    try:
        raw = _claude_call(settings, system, user, client=claude_client)
        return _extract_json(raw)
    except (ClaudeServiceError, ValueError, json.JSONDecodeError) as exc:
        logger.error("scaffolding analysis failed: %s", exc)
        return {"_error": str(exc)}


# ---------- 3) Explanation quality + PCK ----------

def analyse_explanation_quality(
    *,
    turns: list[Turn],
    unit_config: UnitConfig,
    settings: Settings | None = None,
    claude_client=None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    diagnostic = load_diagnostic("explanation_quality.yaml")
    variables = {
        "unit_name": unit_config.unit_name,
        "learning_goals": unit_config.learning_goals,
        "student_turns_with_context": _format_transcript(turns),
    }
    user = assemble_prompt(diagnostic, variables)
    system = "당신은 Learning by Teaching 과 PCK 이론에 정통한 분석가입니다. 반드시 JSON만 출력하세요."
    try:
        raw = _claude_call(settings, system, user, client=claude_client)
        return _extract_json(raw)
    except (ClaudeServiceError, ValueError, json.JSONDecodeError) as exc:
        logger.error("explanation quality analysis failed: %s", exc)
        return {"_error": str(exc)}


# ---------- 4) Concept map change (pre vs post) ----------

def analyse_concept_map_change(
    *,
    pre_map: ConceptMap,
    post_map: ConceptMap,
    unit_config: UnitConfig,
    misconceptions_addressed: list[str] | None = None,
    settings: Settings | None = None,
    claude_client=None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    diagnostic = load_diagnostic("concept_map_change.yaml")

    pre_h = compute_hierarchy(pre_map)
    post_h = compute_hierarchy(post_map)
    pre_score = score_concept_map(pre_map, hierarchy=pre_h)
    post_score = score_concept_map(post_map, hierarchy=post_h)

    pre_fmt = _format_concept_map(pre_map)
    post_fmt = _format_concept_map(post_map)

    variables = {
        "unit_name": unit_config.unit_name,
        "learning_goals": unit_config.learning_goals,
        "pre_concepts": pre_fmt["concepts"],
        "pre_propositions": pre_fmt["propositions"],
        "pre_cross_links": pre_fmt["cross_links"],
        "pre_examples": pre_fmt["examples"],
        "post_concepts": post_fmt["concepts"],
        "post_propositions": post_fmt["propositions"],
        "post_cross_links": post_fmt["cross_links"],
        "post_examples": post_fmt["examples"],
        "pre_score": pre_score.total,
        "post_score": post_score.total,
        "pre_prop_count": pre_score.valid_proposition_count,
        "pre_levels": pre_score.max_hierarchy_level,
        "pre_cross_count": pre_score.cross_link_count,
        "pre_ex_count": pre_score.example_count,
        "post_prop_count": post_score.valid_proposition_count,
        "post_levels": post_score.max_hierarchy_level,
        "post_cross_count": post_score.cross_link_count,
        "post_ex_count": post_score.example_count,
        "misconceptions_addressed": misconceptions_addressed or [],
    }
    user = assemble_prompt(diagnostic, variables)
    system = "당신은 Novak 개념도 이론에 정통한 개념 변화 연구자입니다. 반드시 JSON만 출력하세요."
    try:
        raw = _claude_call(settings, system, user, client=claude_client)
        parsed = _extract_json(raw)
    except (ClaudeServiceError, ValueError, json.JSONDecodeError) as exc:
        logger.error("concept map change analysis failed: %s", exc)
        parsed = {"_error": str(exc)}

    # Always attach computed score delta so downstream (PDF) has a value
    # even if Claude failed.
    parsed.setdefault(
        "score_change",
        {
            "pre": pre_score.total,
            "post": post_score.total,
            "delta": round(post_score.total - pre_score.total, 2),
        },
    )
    parsed["_pre_score_breakdown"] = pre_score.model_dump()
    parsed["_post_score_breakdown"] = post_score.model_dump()
    return parsed


# ---------- 5) Reflection answer analysis ----------

def analyse_reflection_answers(
    *,
    reflection_answers: dict[str, str],
    unit_config: UnitConfig,
    transcript_summary: str,
    concept_map_summary: str,
    settings: Settings | None = None,
    claude_client=None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    diagnostic = load_diagnostic("reflection_analysis.yaml")
    formatted = "\n\n".join(
        f"[{qid}]\n{answer}" for qid, answer in reflection_answers.items()
    )
    variables = {
        "transcript_summary": transcript_summary,
        "concept_map_summary": concept_map_summary,
        "reflection_answers": formatted,
    }
    user = assemble_prompt(diagnostic, variables)
    system = "당신은 교사교육 성찰저널 분석에 능한 질적 연구자입니다. 반드시 JSON만 출력하세요."
    try:
        raw = _claude_call(settings, system, user, client=claude_client)
        return _extract_json(raw)
    except (ClaudeServiceError, ValueError, json.JSONDecodeError) as exc:
        logger.error("reflection analysis failed: %s", exc)
        return {"_error": str(exc)}
