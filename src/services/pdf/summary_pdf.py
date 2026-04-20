"""Build the 2-page instructor summary PDF."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
)

from src.models.schemas import UnitConfig
from src.services.pdf._common import (
    bullet_list,
    esc,
    image_from_bytes,
    kv_table,
    labeled_callout,
    rubric_table,
    section_heading,
    sub_heading,
    vspace,
)
from src.services.pdf.charts import (
    render_misconception_states,
    render_novak_score_bars,
    render_rubric_donut,
)
from src.services.pdf.styles import build_styles

logger = logging.getLogger(__name__)

PAGE_MARGIN = 1.8 * cm


def _safe(d: dict | None, *keys, default=None) -> Any:
    """Traverse nested dicts safely, returning default for any missing key."""

    cur: Any = d or {}
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, {}) if k != keys[-1] else cur.get(k, default)
    return cur if cur is not None else default


def build_summary_pdf(
    *,
    analysis: dict[str, Any],
    unit_config: UnitConfig,
    student_id: str,
    session_id: str,
    start_time: str,
    end_time: str,
) -> bytes:
    """Render the 2-page summary report and return PDF bytes."""

    styles = build_styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title=f"요약 리포트 — {student_id} — {unit_config.unit_name}",
    )

    story: list = []

    # ========== Page 1 — overview ==========

    story.append(Paragraph("예비교사 과학 설명 훈련 — 요약 리포트", styles["H1KR"]))
    story.append(
        Paragraph(
            f"{esc(unit_config.subject)} · {esc(unit_config.unit_name)}",
            styles["MutedKR"],
        )
    )
    story.append(vspace(0.3))

    rule_based = analysis.get("rule_based") or {}
    turn_stats = rule_based.get("turn_statistics") or {}
    story.append(
        kv_table(
            [
                ("학생 ID", student_id),
                ("단원", unit_config.unit_name),
                ("페르소나", unit_config.persona_name),
                ("시작", start_time),
                ("종료", end_time),
                ("총 턴 수", str(turn_stats.get("total_turns", 0))),
                (
                    "학생 발화",
                    f"{(turn_stats.get('student') or {}).get('turn_count', 0)}회 · "
                    f"평균 {(turn_stats.get('student') or {}).get('avg_length', 0)}자",
                ),
                ("세션 ID", session_id),
            ],
            styles,
        )
    )
    story.append(vspace(0.4))

    # Score + donut row (two half-width images stacked as Platypus doesn't lay
    # them side-by-side easily; a KeepInFrame would work but we keep it simple).
    story.append(section_heading("성과 개요", styles))

    concept_map_change = analysis.get("concept_map_change") or {}
    score_change = concept_map_change.get("score_change") or {}
    pre_score = float(score_change.get("pre", 0) or 0)
    post_score = float(score_change.get("post", 0) or 0)
    try:
        bar_png = render_novak_score_bars(pre_score, post_score)
        story.append(image_from_bytes(bar_png, width_cm=10))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Novak bar render failed: %s", exc)
        story.append(
            Paragraph(f"(Novak 점수 차트 생성 실패: {esc(exc)})", styles["MutedKR"])
        )

    story.append(vspace(0.3))

    achieved = rule_based.get("rubric_items_achieved") or {}
    rubric_labels = {it.item_id: it.description for it in unit_config.rubric_items}
    try:
        donut_png = render_rubric_donut(achieved)
        story.append(image_from_bytes(donut_png, width_cm=8))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rubric donut render failed: %s", exc)

    story.append(vspace(0.2))
    story.append(rubric_table(achieved, rubric_labels, styles))

    # ========== Page 2 — strengths / growth / misconception states ==========
    story.append(PageBreak())

    explanation = analysis.get("explanation_quality") or {}
    strengths: list[str] = list(explanation.get("strengths") or [])[:3]
    growth: list[str] = list(explanation.get("growth_points") or [])[:3]

    story.append(section_heading("강점과 성장 포인트", styles))
    story.append(sub_heading("강점", styles))
    for s in strengths or ["(분석 결과 없음)"]:
        story.append(labeled_callout("강점", s, styles))
    story.append(vspace(0.2))
    story.append(sub_heading("개선 포인트", styles))
    for s in growth or ["(분석 결과 없음)"]:
        story.append(labeled_callout("개선", s, styles))
    story.append(vspace(0.3))

    story.append(section_heading("오개념 최종 상태", styles))
    trajectories = (analysis.get("misconceptions") or {}).get("trajectories") or []
    try:
        misc_png = render_misconception_states(trajectories)
        story.append(image_from_bytes(misc_png, width_cm=15))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Misconception chart render failed: %s", exc)
        story.append(Paragraph(f"(차트 생성 실패: {esc(exc)})", styles["MutedKR"]))

    story.append(vspace(0.3))

    story.append(section_heading("주목 순간 (Notable moments)", styles))
    moments = list((explanation.get("notable_moments") or []))[:5]
    if moments:
        for m in moments:
            if not isinstance(m, dict):
                continue
            turn = m.get("turn", "-")
            excerpt = m.get("excerpt", "")
            why = m.get("why_notable", "")
            story.append(
                Paragraph(
                    f"<b>턴 {esc(turn)}</b> · <i>{esc(excerpt)}</i><br/>"
                    f"→ {esc(why)}",
                    styles["Callout"],
                )
            )
    else:
        for para in bullet_list([], styles, empty_text="(분석 결과 없음)"):
            story.append(para)

    story.append(vspace(0.3))

    # Summary sentence
    summary_blurb = (analysis.get("misconceptions") or {}).get(
        "overall_conceptual_change_summary"
    ) or "(종합 요약 없음)"
    story.append(section_heading("한 문단 요약", styles))
    story.append(Paragraph(esc(summary_blurb), styles["BodyKR"]))

    doc.build(story)
    return buf.getvalue()
