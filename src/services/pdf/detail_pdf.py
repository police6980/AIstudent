"""Build the detailed multi-page instructor report PDF."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

from src.models.concept_map import ConceptMap
from src.models.enums import Speaker
from src.models.schemas import Turn, UnitConfig
from src.services.concept_maps.novak_scoring import (
    compute_hierarchy,
    score_concept_map,
)
from src.services.concept_maps.visualization import render_concept_map_png
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
    render_explanation_trajectory,
    render_misconception_states,
    render_novak_score_bars,
    render_rubric_donut,
)
from src.services.pdf.styles import build_styles

logger = logging.getLogger(__name__)

PAGE_MARGIN = 1.8 * cm


def _student_turn_indices_with_rubric_hit(analysis: dict[str, Any]) -> set[int]:
    hits = (analysis.get("rule_based") or {}).get("rubric_hits") or []
    return {int(h.get("first_turn_index", -1)) for h in hits if isinstance(h, dict)}


def _misconception_turn_indices(analysis: dict[str, Any]) -> set[int]:
    indices: set[int] = set()
    trajectories = (analysis.get("misconceptions") or {}).get("trajectories") or []
    for tj in trajectories:
        if not isinstance(tj, dict):
            continue
        for ev in tj.get("key_events") or []:
            if isinstance(ev, dict) and ev.get("turn") is not None:
                try:
                    indices.add(int(ev["turn"]))
                except (TypeError, ValueError):
                    continue
    return indices


def _transcript_paragraph(t: Turn, idx: int, rubric_idx: set[int], misconception_idx: set[int], styles):
    role = "학생" if t.speaker == Speaker.STUDENT else "AI"
    ts = t.timestamp.strftime("%H:%M:%S") if getattr(t, "timestamp", None) else ""
    prefix = f"<b>[턴 {idx}]</b> <font color='#6B7280'>{esc(ts)}</font> <b>{esc(role)}:</b> "

    style = styles["BodySmallKR"]
    if idx in misconception_idx:
        style = styles["Warning"]
    elif idx in rubric_idx:
        style = styles["Callout"]

    return Paragraph(prefix + esc(t.content), style)


def build_detail_pdf(
    *,
    analysis: dict[str, Any],
    unit_config: UnitConfig,
    student_id: str,
    session_id: str,
    start_time: str,
    end_time: str,
    turns: list[Turn],
    pre_map: ConceptMap | None,
    post_map: ConceptMap | None,
    initial_diagnosis: dict[str, Any] | None,
    reflection_answers: dict[str, str] | None,
    reflection_questions: list,  # list[ReflectionQuestion]
) -> bytes:
    """Render the detailed report and return PDF bytes."""

    styles = build_styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title=f"상세 리포트 — {student_id} — {unit_config.unit_name}",
    )

    story: list = []

    # ===== Cover =====
    story.append(Paragraph("예비교사 과학 설명 훈련 — 상세 리포트", styles["H1KR"]))
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
                ("담당 교수", unit_config.instructor_name),
                ("단원", unit_config.unit_name),
                ("페르소나", unit_config.persona_name),
                ("대상 학년(가르침)", unit_config.target_grade_for_teaching or "(지정 없음)"),
                ("시작", start_time),
                ("종료", end_time),
                ("총 턴", str(turn_stats.get("total_turns", 0))),
                ("학생 발화 수/평균 길이",
                 f"{(turn_stats.get('student') or {}).get('turn_count', 0)}회 / "
                 f"{(turn_stats.get('student') or {}).get('avg_length', 0)}자"),
                ("AI 발화 수/평균 길이",
                 f"{(turn_stats.get('ai') or {}).get('turn_count', 0)}회 / "
                 f"{(turn_stats.get('ai') or {}).get('avg_length', 0)}자"),
                ("세션 ID", session_id),
            ],
            styles,
        )
    )
    story.append(PageBreak())

    # ===== 1) 루브릭 =====
    story.append(section_heading("1. 루브릭 달성", styles))
    achieved = rule_based.get("rubric_items_achieved") or {}
    rubric_labels = {it.item_id: it.description for it in unit_config.rubric_items}
    try:
        story.append(image_from_bytes(render_rubric_donut(achieved), width_cm=7))
    except Exception as exc:  # noqa: BLE001
        logger.warning("rubric donut failed: %s", exc)
    story.append(vspace(0.2))
    story.append(rubric_table(achieved, rubric_labels, styles))

    hits = rule_based.get("rubric_hits") or []
    if hits:
        story.append(vspace(0.2))
        story.append(sub_heading("루브릭 첫 달성 지점", styles))
        for h in hits:
            if not isinstance(h, dict):
                continue
            story.append(
                Paragraph(
                    f"<b>{esc(h.get('item_id'))}</b> · 턴 {esc(h.get('first_turn_index'))} · "
                    f"키워드 '{esc(h.get('keyword_matched'))}' · 총 {esc(h.get('hit_count'))}회<br/>"
                    f"<i>{esc(h.get('first_turn_excerpt'))}</i>",
                    styles["Callout"],
                )
            )

    # ===== 2) 개념도 전/후 =====
    story.append(PageBreak())
    story.append(section_heading("2. 개념도 변화 (Novak)", styles))

    concept_map_change = analysis.get("concept_map_change") or {}
    score_change = concept_map_change.get("score_change") or {}
    pre_score_val = float(score_change.get("pre", 0) or 0)
    post_score_val = float(score_change.get("post", 0) or 0)

    try:
        story.append(
            image_from_bytes(render_novak_score_bars(pre_score_val, post_score_val), width_cm=10)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("novak bar failed: %s", exc)

    story.append(vspace(0.2))

    if pre_map is not None:
        story.append(sub_heading("초기 개념도", styles))
        try:
            pre_h = compute_hierarchy(pre_map)
            pre_score = score_concept_map(pre_map, hierarchy=pre_h)
            story.append(
                image_from_bytes(
                    render_concept_map_png(pre_map, hierarchy=pre_h, title="초기 개념도"),
                    width_cm=15,
                )
            )
            story.append(
                Paragraph(
                    f"개념 {len(pre_map.concepts)} · 명제 {pre_score.valid_proposition_count} · "
                    f"교차연결 {pre_score.cross_link_count} · 예시 {pre_score.example_count} · "
                    f"위계 최대 Lv {pre_score.max_hierarchy_level} · "
                    f"<b>총점 {pre_score.total}</b>",
                    styles["MutedKR"],
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pre map render failed: %s", exc)
            story.append(Paragraph(f"(초기 개념도 시각화 실패: {esc(exc)})", styles["MutedKR"]))

    if post_map is not None:
        story.append(PageBreak())
        story.append(sub_heading("사후 개념도", styles))
        try:
            post_h = compute_hierarchy(post_map)
            post_score = score_concept_map(post_map, hierarchy=post_h)
            story.append(
                image_from_bytes(
                    render_concept_map_png(post_map, hierarchy=post_h, title="사후 개념도"),
                    width_cm=15,
                )
            )
            story.append(
                Paragraph(
                    f"개념 {len(post_map.concepts)} · 명제 {post_score.valid_proposition_count} · "
                    f"교차연결 {post_score.cross_link_count} · 예시 {post_score.example_count} · "
                    f"위계 최대 Lv {post_score.max_hierarchy_level} · "
                    f"<b>총점 {post_score.total}</b>",
                    styles["MutedKR"],
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("post map render failed: %s", exc)
            story.append(Paragraph(f"(사후 개념도 시각화 실패: {esc(exc)})", styles["MutedKR"]))

    # LLM-derived change analysis
    changes_by_type = (concept_map_change.get("changes_by_type") or {})
    cross_links = concept_map_change.get("key_emerging_cross_links") or []
    if changes_by_type or cross_links:
        story.append(vspace(0.3))
        story.append(sub_heading("변화 유형별 요약", styles))
        for type_key, label in [
            ("addition", "추가"),
            ("elaboration", "정교화"),
            ("restructuring", "재구조화"),
            ("integration", "통합(새 교차연결)"),
            ("correction", "오개념 교정"),
            ("persistence", "오개념 지속"),
        ]:
            items = changes_by_type.get(type_key) or []
            if not items:
                continue
            story.append(Paragraph(f"<b>{label}</b>", styles["BodyKR"]))
            for it in items:
                if isinstance(it, dict):
                    parts = [f"{k}: {v}" for k, v in it.items()]
                    story.append(Paragraph(" · ".join(map(esc, parts)), styles["BodySmallKR"]))
                else:
                    story.append(Paragraph(esc(it), styles["BodySmallKR"]))

        if cross_links:
            story.append(vspace(0.2))
            story.append(sub_heading("주목할 새 교차연결", styles))
            for cl in cross_links:
                if not isinstance(cl, dict):
                    continue
                story.append(
                    Paragraph(
                        f"<b>{esc(cl.get('from'))}</b> —[{esc(cl.get('linking'))}]→ "
                        f"<b>{esc(cl.get('to'))}</b><br/>"
                        f"<i>{esc(cl.get('why_notable'))}</i>",
                        styles["Callout"],
                    )
                )

    # ===== 3) 초기 진단 (Vygotsky ZPD 기반) =====
    story.append(PageBreak())
    story.append(section_heading("3. 초기 개념도 진단 (ZPD)", styles))
    if initial_diagnosis:
        story.append(
            Paragraph(
                f"<b>수준 판정:</b> {esc(initial_diagnosis.get('level', '-'))}", styles["BodyKR"]
            )
        )
        story.append(
            Paragraph(
                esc(initial_diagnosis.get("level_justification", "")), styles["BodyKR"]
            )
        )
        story.append(vspace(0.2))
        story.append(sub_heading("감지된 오개념", styles))
        miscons = initial_diagnosis.get("detected_misconceptions") or []
        if miscons:
            for m in miscons:
                if isinstance(m, dict):
                    story.append(
                        Paragraph(
                            f"• <b>{esc(m.get('misconception'))}</b> — "
                            f"{esc(m.get('evidence_in_map'))}",
                            styles["Warning"],
                        )
                    )
                else:
                    story.append(Paragraph(f"• {esc(m)}", styles["Warning"]))
        else:
            story.append(Paragraph("(없음)", styles["MutedKR"]))

        story.append(vspace(0.2))
        story.append(sub_heading("빠진 핵심 개념", styles))
        for p in bullet_list(list(initial_diagnosis.get("missing_core_concepts") or []), styles):
            story.append(p)

        story.append(vspace(0.2))
        story.append(sub_heading("ZPD 내 학습 목표", styles))
        for p in bullet_list(list(initial_diagnosis.get("zpd_targets") or []), styles):
            story.append(p)

        story.append(vspace(0.2))
        story.append(
            labeled_callout(
                "AI에게 권장된 첫 질문",
                initial_diagnosis.get("recommended_first_question", ""),
                styles,
            )
        )
    else:
        story.append(Paragraph("(진단 결과 없음)", styles["MutedKR"]))

    # ===== 4) 오개념 동태 =====
    story.append(PageBreak())
    story.append(section_heading("4. 오개념 동태", styles))
    trajectories = (analysis.get("misconceptions") or {}).get("trajectories") or []
    try:
        story.append(image_from_bytes(render_misconception_states(trajectories), width_cm=14))
    except Exception as exc:  # noqa: BLE001
        logger.warning("misconception chart failed: %s", exc)

    for tj in trajectories:
        if not isinstance(tj, dict):
            continue
        story.append(vspace(0.2))
        story.append(
            Paragraph(
                f"<b>{esc(tj.get('misconception'))}</b> "
                f"({esc(tj.get('source'))}) → 최종 상태: "
                f"<b>{esc(tj.get('final_state'))}</b>",
                styles["Callout"],
            )
        )
        story.append(
            Paragraph(
                esc(tj.get("final_state_justification", "")), styles["BodySmallKR"]
            )
        )
        events = tj.get("key_events") or []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            story.append(
                Paragraph(
                    f"턴 {esc(ev.get('turn'))} · <b>{esc(ev.get('speaker'))}</b> · "
                    f"{esc(ev.get('event'))}<br/><i>{esc(ev.get('excerpt'))}</i>",
                    styles["BodySmallKR"],
                )
            )

    overall_sum = (analysis.get("misconceptions") or {}).get(
        "overall_conceptual_change_summary"
    )
    if overall_sum:
        story.append(vspace(0.3))
        story.append(Paragraph(esc(overall_sum), styles["BodyKR"]))

    # ===== 5) 비계 품질 =====
    story.append(PageBreak())
    story.append(section_heading("5. AI 비계 품질 (Vygotsky)", styles))
    scaffolding = analysis.get("scaffolding_quality") or {}
    if "_error" in scaffolding:
        story.append(Paragraph(f"(분석 실패: {esc(scaffolding['_error'])})", styles["Warning"]))
    else:
        story.append(
            Paragraph(
                f"<b>종합 품질:</b> {esc(scaffolding.get('overall_scaffolding_quality', '-'))}<br/>"
                f"<b>Fading 패턴:</b> {esc(scaffolding.get('fading_pattern', '-'))}",
                styles["BodyKR"],
            )
        )
        strong_moments = scaffolding.get("top_3_strong_scaffolding_moments") or []
        if strong_moments:
            story.append(vspace(0.2))
            story.append(sub_heading("인상적이었던 비계 순간", styles))
            for m in strong_moments:
                if isinstance(m, dict):
                    story.append(
                        Paragraph(
                            f"턴 {esc(m.get('turn'))} — {esc(m.get('reason'))}",
                            styles["Callout"],
                        )
                    )
        problematic = scaffolding.get("top_3_problematic_moments") or []
        if problematic:
            story.append(vspace(0.2))
            story.append(sub_heading("개선 여지가 있었던 순간", styles))
            for m in problematic:
                if isinstance(m, dict):
                    story.append(
                        Paragraph(
                            f"턴 {esc(m.get('turn'))} — {esc(m.get('reason'))}",
                            styles["Warning"],
                        )
                    )

    # ===== 6) 설명 품질 + PCK =====
    story.append(PageBreak())
    story.append(section_heading("6. 설명 품질 · PCK", styles))
    explanation = analysis.get("explanation_quality") or {}
    traj = explanation.get("explanation_quality_trajectory") or []
    try:
        story.append(image_from_bytes(render_explanation_trajectory(traj), width_cm=15))
    except Exception as exc:  # noqa: BLE001
        logger.warning("explanation trajectory failed: %s", exc)

    pck = explanation.get("pck_observations") or {}
    if pck:
        story.append(vspace(0.2))
        story.append(sub_heading("PCK 관찰", styles))
        for dim, val in pck.items():
            if isinstance(val, dict):
                parts = [f"<b>{dim}</b>"]
                for k, v in val.items():
                    parts.append(f"{k}: {v}")
                story.append(Paragraph(" · ".join(map(esc, parts)), styles["BodySmallKR"]))
            else:
                story.append(Paragraph(f"<b>{esc(dim)}</b>: {esc(val)}", styles["BodySmallKR"]))

    comparison = explanation.get("first_vs_last_explanation_comparison") or {}
    if comparison:
        story.append(vspace(0.2))
        story.append(sub_heading("첫 설명 vs 마지막 설명", styles))
        story.append(
            Paragraph(
                f"<b>초반:</b> <i>{esc(comparison.get('early_excerpt', ''))}</i>",
                styles["BodySmallKR"],
            )
        )
        story.append(
            Paragraph(
                f"<b>후반:</b> <i>{esc(comparison.get('late_excerpt', ''))}</i>",
                styles["BodySmallKR"],
            )
        )
        story.append(
            Paragraph(
                f"변화: {esc(comparison.get('observed_change', ''))}", styles["BodyKR"]
            )
        )

    story.append(vspace(0.3))
    story.append(sub_heading("강점", styles))
    for p in bullet_list(list(explanation.get("strengths") or []), styles):
        story.append(p)
    story.append(vspace(0.1))
    story.append(sub_heading("개선 포인트", styles))
    for p in bullet_list(list(explanation.get("growth_points") or []), styles):
        story.append(p)

    # ===== 7) 성찰 응답 + 분석 =====
    story.append(PageBreak())
    story.append(section_heading("7. 성찰 응답 및 분석", styles))
    reflection_analysis = analysis.get("reflection") or {}
    per_question = reflection_analysis.get("per_question_analysis") or []
    per_question_by_id = {
        q.get("question_id"): q for q in per_question if isinstance(q, dict)
    }

    for q in reflection_questions:
        story.append(vspace(0.2))
        story.append(sub_heading(q.title, styles))
        story.append(Paragraph(f"<i>{esc(q.prompt)}</i>", styles["MutedKR"]))
        answer = (reflection_answers or {}).get(q.id, "").strip() or "(무응답)"
        story.append(Paragraph(esc(answer), styles["Callout"]))

        meta = per_question_by_id.get(q.id)
        if meta:
            story.append(
                Paragraph(
                    f"메타인지 깊이 {esc(meta.get('metacognitive_depth', '-'))} · "
                    f"근거 기반 {esc(meta.get('evidence_grounding', '-'))} · "
                    f"통찰 {esc(meta.get('depth_of_insight', '-'))} · "
                    f"자기관찰 정확도 {esc(meta.get('self_observation_accuracy', '-'))}",
                    styles["MutedKR"],
                )
            )
            note = meta.get("analytic_summary") or meta.get("accuracy_note")
            if note:
                story.append(Paragraph(esc(note), styles["BodySmallKR"]))

    cross_pat = reflection_analysis.get("cross_question_patterns")
    if cross_pat:
        story.append(vspace(0.3))
        story.append(sub_heading("응답들을 관통하는 패턴", styles))
        story.append(Paragraph(esc(cross_pat), styles["BodyKR"]))
    research_note = reflection_analysis.get("research_value_notes")
    if research_note:
        story.append(
            Paragraph(
                f"<b>연구 자료 가치:</b> {esc(research_note)}", styles["BodyKR"]
            )
        )

    # ===== 8) 전체 전사 =====
    story.append(PageBreak())
    story.append(section_heading("8. 전체 전사", styles))
    rubric_idx = _student_turn_indices_with_rubric_hit(analysis)
    miscon_idx = _misconception_turn_indices(analysis)
    story.append(
        Paragraph(
            "파란 배경 = 루브릭 첫 달성 · 빨간 배경 = 오개념 관련 이벤트",
            styles["MutedKR"],
        )
    )
    story.append(vspace(0.1))
    for idx, t in enumerate(turns):
        story.append(_transcript_paragraph(t, idx, rubric_idx, miscon_idx, styles))

    # ===== 부록 =====
    story.append(PageBreak())
    story.append(section_heading("부록. 원본 단원 설정", styles))
    story.append(
        kv_table(
            [
                ("단원 코드", unit_config.unit_code),
                ("페르소나 이름", unit_config.persona_name),
                ("페르소나 역할", unit_config.persona_role),
            ],
            styles,
        )
    )
    story.append(vspace(0.2))
    story.append(sub_heading("학습 목표", styles))
    for p in bullet_list(list(unit_config.learning_goals), styles):
        story.append(p)
    story.append(vspace(0.1))
    story.append(sub_heading("알려진 오개념", styles))
    for p in bullet_list(list(unit_config.common_misconceptions), styles):
        story.append(p)
    story.append(vspace(0.1))
    story.append(sub_heading("AI 초기 오개념", styles))
    for p in bullet_list(list(unit_config.persona_initial_misconceptions), styles):
        story.append(p)

    errors = analysis.get("errors") or []
    if errors:
        story.append(PageBreak())
        story.append(section_heading("분석 중 발생한 오류 로그", styles))
        for e in errors:
            story.append(Paragraph(f"• {esc(e)}", styles["Warning"]))

    doc.build(story)
    return buf.getvalue()
