"""Generate Summary + Detail PDFs for a completed session.

Usage:
    paths = generate_reports_for_session(session_id)
    # paths.summary / paths.detail are Paths to the written files.

Files land under REPORT_DIR / session_id / (summary.pdf, detail.pdf).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config.settings import get_settings
from src.db.repository import SessionRepository
from src.models.concept_map import ConceptMap
from src.models.schemas import UnitConfig
from src.services.diagnostics import load_reflection_questions
from src.services.pdf.detail_pdf import build_detail_pdf
from src.services.pdf.summary_pdf import build_summary_pdf

logger = logging.getLogger(__name__)


@dataclass
class ReportPaths:
    summary: Path
    detail: Path


def _fmt_ts(dt: Optional[datetime]) -> str:
    if dt is None:
        return "(진행 중)"
    return dt.strftime("%Y-%m-%d %H:%M")


def _report_dir(session_id: str, student_id: str, unit_code: str) -> Path:
    settings = get_settings()
    root = Path(settings.report_dir)
    # Per-session subdir so rerun overwrites cleanly and students find their files.
    out = root / f"{unit_code}_{student_id}_{session_id[:8]}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def generate_reports_for_session(
    session_id: str,
    *,
    repo: Optional[SessionRepository] = None,
) -> ReportPaths:
    """Render both PDFs for the given session and write them to REPORT_DIR.

    Raises LookupError if the session doesn't exist.
    Does NOT require the session to be completed — partial reports are allowed
    so instructors can spot-check in progress (but the analysis will be empty).
    """

    repo = repo or SessionRepository()
    row = repo.get_session(session_id)
    if row is None:
        raise LookupError(f"Session not found: {session_id}")

    unit_config = UnitConfig.model_validate(row.unit_config_json)
    turns = repo.get_turns(session_id)
    analysis = row.analysis_json or {}
    pre_map = (
        ConceptMap.model_validate(row.pre_concept_map_json)
        if row.pre_concept_map_json
        else None
    )
    post_map = (
        ConceptMap.model_validate(row.post_concept_map_json)
        if row.post_concept_map_json
        else None
    )
    initial_diagnosis = row.initial_diagnosis_json or {}
    reflection_answers = row.reflection_answers_json or {}
    reflection_questions = load_reflection_questions()

    common_kwargs = dict(
        analysis=analysis,
        unit_config=unit_config,
        student_id=row.student_id,
        session_id=session_id,
        start_time=_fmt_ts(row.start_time),
        end_time=_fmt_ts(row.end_time),
    )

    logger.info("Building summary PDF for session %s", session_id)
    summary_bytes = build_summary_pdf(**common_kwargs)

    logger.info("Building detail PDF for session %s", session_id)
    detail_bytes = build_detail_pdf(
        **common_kwargs,
        turns=turns,
        pre_map=pre_map,
        post_map=post_map,
        initial_diagnosis=initial_diagnosis,
        reflection_answers=reflection_answers,
        reflection_questions=reflection_questions,
    )

    out_dir = _report_dir(session_id, row.student_id, row.unit_code)
    summary_path = out_dir / "summary.pdf"
    detail_path = out_dir / "detail.pdf"
    summary_path.write_bytes(summary_bytes)
    detail_path.write_bytes(detail_bytes)
    logger.info(
        "Wrote reports for session %s: %s, %s",
        session_id, summary_path, detail_path,
    )
    return ReportPaths(summary=summary_path, detail=detail_path)
