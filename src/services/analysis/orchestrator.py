"""Run the full post-session analysis pipeline and store results.

Input: session_id of a COMPLETED session.
Output: a dict written to session.analysis_json, consumed by the B5 PDF generator.

Pipeline:
    1. Load session row + unit_config + turns + pre/post maps + reflection answers.
    2. Rule-based analysis (fast, no LLM).
    3. LLM analyses (misconception, scaffolding, explanation, concept_map_change,
       reflection) — run sequentially; each can fail independently and still
       produce a partial report.
    4. Merge everything into one dict and save.

Failures never raise — they're serialised as `{"_error": ...}` so the PDF
always renders something useful for the instructor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.config.settings import Settings, get_settings
from src.db.repository import SessionRepository
from src.models.concept_map import ConceptMap
from src.models.enums import SessionStatus, Speaker
from src.models.schemas import Turn, UnitConfig
from src.services.analysis.llm_analyzers import (
    analyse_concept_map_change,
    analyse_explanation_quality,
    analyse_misconceptions,
    analyse_reflection_answers,
    analyse_scaffolding_quality,
)
from src.services.analysis.rule_based import analyse_turns_rule_based

logger = logging.getLogger(__name__)


@dataclass
class AnalysisBundle:
    """Full analysis result stored on session.analysis_json."""

    generated_at: str
    session_id: str
    student_id: str
    unit_code: str
    rule_based: dict[str, Any] = field(default_factory=dict)
    misconceptions: dict[str, Any] = field(default_factory=dict)
    scaffolding_quality: dict[str, Any] = field(default_factory=dict)
    explanation_quality: dict[str, Any] = field(default_factory=dict)
    concept_map_change: dict[str, Any] = field(default_factory=dict)
    reflection: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "session_id": self.session_id,
            "student_id": self.student_id,
            "unit_code": self.unit_code,
            "rule_based": self.rule_based,
            "misconceptions": self.misconceptions,
            "scaffolding_quality": self.scaffolding_quality,
            "explanation_quality": self.explanation_quality,
            "concept_map_change": self.concept_map_change,
            "reflection": self.reflection,
            "errors": self.errors,
        }


def _transcript_summary(turns: list[Turn], max_chars: int = 1200) -> str:
    """Very light transcript summary for reflection-analysis prompt."""

    out = []
    for i, t in enumerate(turns):
        role = "학생" if t.speaker == Speaker.STUDENT else "AI"
        line = f"[{i}] {role}: {t.content}"
        out.append(line)
    joined = "\n".join(out)
    if len(joined) > max_chars:
        joined = joined[:max_chars] + "\n...(생략)"
    return joined


def _map_summary(cmap: ConceptMap | None) -> str:
    if cmap is None:
        return "(없음)"
    return (
        f"개념 {len(cmap.concepts)}개, 명제 {len(cmap.propositions)}개, "
        f"교차연결 {len(cmap.cross_links)}개, 예시 {len(cmap.examples)}개"
    )


def _load_session_context(
    session_id: str, repo: SessionRepository
):
    """Pull everything the analyzers need from the DB in one pass."""

    row = repo.get_session(session_id)
    if row is None:
        raise LookupError(f"Session not found: {session_id}")

    unit_config = UnitConfig.model_validate(row.unit_config_json)
    turns = repo.get_turns(session_id)

    pre_map = None
    post_map = None
    if row.pre_concept_map_json:
        pre_map = ConceptMap.model_validate(row.pre_concept_map_json)
    if row.post_concept_map_json:
        post_map = ConceptMap.model_validate(row.post_concept_map_json)

    initial_diag = row.initial_diagnosis_json or {}
    initial_student_miscons: list[str] = []
    for m in initial_diag.get("detected_misconceptions") or []:
        if isinstance(m, dict) and m.get("misconception"):
            initial_student_miscons.append(str(m["misconception"]))
        elif isinstance(m, str):
            initial_student_miscons.append(m)

    reflection_answers = row.reflection_answers_json or {}
    return row, unit_config, turns, pre_map, post_map, initial_student_miscons, reflection_answers


def run_full_analysis(
    session_id: str,
    *,
    repo: SessionRepository | None = None,
    settings: Settings | None = None,
    claude_client=None,
) -> AnalysisBundle:
    """Run the full analysis pipeline and persist results on the session row.

    Failure of any single analyzer is logged and recorded in `bundle.errors`,
    but the function never raises — so the instructor always gets whatever
    analyses did succeed.
    """

    repo = repo or SessionRepository()
    settings = settings or get_settings()

    (
        row,
        unit_config,
        turns,
        pre_map,
        post_map,
        initial_student_miscons,
        reflection_answers,
    ) = _load_session_context(session_id, repo)

    bundle = AnalysisBundle(
        generated_at=datetime.utcnow().isoformat() + "Z",
        session_id=session_id,
        student_id=row.student_id,
        unit_code=row.unit_code,
    )

    if row.status != SessionStatus.COMPLETED.value:
        bundle.errors.append(
            f"세션이 아직 완료 상태가 아닙니다 (current status: {row.status}). "
            "완료된 세션에서만 리포트를 생성할 수 있어요."
        )
        logger.warning("run_full_analysis called on non-completed session %s", session_id)

    # ---- 1) Rule-based ----
    try:
        rb = analyse_turns_rule_based(turns, unit_config.rubric_items)
        bundle.rule_based = rb.to_dict()
    except Exception as exc:  # noqa: BLE001 - rule-based is pure python, shouldn't fail
        logger.exception("Rule-based analysis failed: %s", exc)
        bundle.errors.append(f"rule_based: {exc}")

    # ---- 2) Misconception tracking (LLM) ----
    try:
        bundle.misconceptions = analyse_misconceptions(
            turns=turns,
            unit_config=unit_config,
            initial_student_misconceptions=initial_student_miscons,
            settings=settings,
            claude_client=claude_client,
        )
        if "_error" in bundle.misconceptions:
            bundle.errors.append(f"misconceptions: {bundle.misconceptions['_error']}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Misconception analysis crashed: %s", exc)
        bundle.misconceptions = {"_error": str(exc)}
        bundle.errors.append(f"misconceptions: {exc}")

    # ---- 3) Scaffolding quality (LLM) ----
    try:
        bundle.scaffolding_quality = analyse_scaffolding_quality(
            turns=turns,
            unit_config=unit_config,
            settings=settings,
            claude_client=claude_client,
        )
        if "_error" in bundle.scaffolding_quality:
            bundle.errors.append(f"scaffolding_quality: {bundle.scaffolding_quality['_error']}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scaffolding quality analysis crashed: %s", exc)
        bundle.scaffolding_quality = {"_error": str(exc)}
        bundle.errors.append(f"scaffolding_quality: {exc}")

    # ---- 4) Explanation quality + PCK (LLM) ----
    try:
        bundle.explanation_quality = analyse_explanation_quality(
            turns=turns,
            unit_config=unit_config,
            settings=settings,
            claude_client=claude_client,
        )
        if "_error" in bundle.explanation_quality:
            bundle.errors.append(f"explanation_quality: {bundle.explanation_quality['_error']}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Explanation quality analysis crashed: %s", exc)
        bundle.explanation_quality = {"_error": str(exc)}
        bundle.errors.append(f"explanation_quality: {exc}")

    # ---- 5) Concept map change (LLM) ----
    if pre_map is None or post_map is None:
        bundle.concept_map_change = {
            "_error": "초기 또는 사후 개념도가 없어 비교 분석을 건너뜁니다."
        }
        bundle.errors.append("concept_map_change: 개념도 부족")
    else:
        try:
            misconceptions_addressed: list[str] = []
            for tj in (bundle.misconceptions.get("trajectories") or []):
                if isinstance(tj, dict) and tj.get("misconception"):
                    misconceptions_addressed.append(str(tj["misconception"]))
            bundle.concept_map_change = analyse_concept_map_change(
                pre_map=pre_map,
                post_map=post_map,
                unit_config=unit_config,
                misconceptions_addressed=misconceptions_addressed,
                settings=settings,
                claude_client=claude_client,
            )
            if "_error" in bundle.concept_map_change and bundle.concept_map_change["_error"]:
                bundle.errors.append(
                    f"concept_map_change: {bundle.concept_map_change['_error']}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Concept map change analysis crashed: %s", exc)
            bundle.concept_map_change = {"_error": str(exc)}
            bundle.errors.append(f"concept_map_change: {exc}")

    # ---- 6) Reflection analysis (LLM) ----
    if not reflection_answers:
        bundle.reflection = {"_error": "성찰 응답이 없어 분석을 건너뜁니다."}
        bundle.errors.append("reflection: 응답 없음")
    else:
        try:
            bundle.reflection = analyse_reflection_answers(
                reflection_answers=reflection_answers,
                unit_config=unit_config,
                transcript_summary=_transcript_summary(turns),
                concept_map_summary=(
                    f"초기: {_map_summary(pre_map)} | 사후: {_map_summary(post_map)}"
                ),
                settings=settings,
                claude_client=claude_client,
            )
            if "_error" in bundle.reflection:
                bundle.errors.append(f"reflection: {bundle.reflection['_error']}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reflection analysis crashed: %s", exc)
            bundle.reflection = {"_error": str(exc)}
            bundle.errors.append(f"reflection: {exc}")

    repo.save_analysis(session_id, bundle.to_dict())
    logger.info(
        "Analysis complete for session %s (errors: %d)", session_id, len(bundle.errors)
    )
    return bundle
