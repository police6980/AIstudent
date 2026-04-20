"""Instructor management UI (accessed via ?admin=true).

Five tabs:
  1) 단원 관리     — list / create / edit / delete unit YAMLs
  2) 성찰 질문     — edit the 5 reflection questions
  3) 진단 프롬프트 — edit diagnostic YAML prompt templates
  4) 참고 자료     — upload / delete theory PDFs/MDs
  5) 세션 조회     — browse completed sessions, download PDFs (Phase B5), unlock

This file keeps each tab's callbacks close together so it can be
read top-to-bottom without jumping around.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

import gradio as gr
import yaml
from pydantic import ValidationError

from src.config.unit_config import UnitConfigError, load_unit_config
from src.models.schemas import RubricItem, UnitConfig
from src.services.diagnostics import (
    ReflectionQuestion,
    list_diagnostics,
    list_reference_materials,
    load_diagnostic,
    load_reflection_questions,
    save_reflection_questions,
)
from src.services.diagnostics.diagnostic_config import save_diagnostic
from src.services.instructor_service import (
    admin_enabled,
    delete_reference,
    delete_unit,
    list_sessions,
    list_units,
    rerun_analysis,
    reset_session_to_in_progress,
    save_reference_upload,
    save_unit_config,
    verify_instructor_password,
)

logger = logging.getLogger(__name__)


def _units_table() -> list[list[Any]]:
    return [
        [u.filename, u.unit_code, u.unit_name, u.persona_name, u.student_count]
        for u in list_units()
    ]


def _sessions_table(unit_filter: str | None = None) -> list[list[Any]]:
    rows = list_sessions(unit_filter if unit_filter else None)
    return [
        [
            r.session_id[:12] + "…",
            r.unit_code,
            r.student_id,
            r.status.value,
            r.start_time.strftime("%Y-%m-%d %H:%M"),
            (r.end_time.strftime("%Y-%m-%d %H:%M") if r.end_time else "-"),
            r.turn_count,
        ]
        for r in rows
    ]


def _diagnostics_choices() -> list[str]:
    return list_diagnostics()


def _reference_list_rows() -> list[list[str]]:
    return [[fn] for fn in list_reference_materials()]


def _parse_rubric_text(text: str) -> list[RubricItem]:
    """Parse the simple rubric edit format (one item per line):

        required | item_id | description | keyword1,keyword2
    """

    items: list[RubricItem] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            raise ValueError(f"루브릭 줄 형식 오류 (필요|ID|설명|키워드): {raw}")
        required = parts[0].lower() in {"true", "1", "필수", "yes", "y"}
        item_id = parts[1]
        description = parts[2]
        keywords = [k.strip() for k in parts[3].split(",")] if len(parts) >= 4 and parts[3] else []
        items.append(
            RubricItem(
                item_id=item_id, description=description, keywords=keywords, required=required
            )
        )
    return items


def _rubric_to_text(items: list[RubricItem]) -> str:
    lines = ["# 한 줄에 하나씩. 형식:  필수여부 | item_id | 설명 | 키워드(쉼표구분)"]
    for it in items:
        req = "필수" if it.required else "선택"
        kws = ",".join(it.keywords)
        lines.append(f"{req} | {it.item_id} | {it.description} | {kws}")
    return "\n".join(lines)


def _bullets_from_text(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _bullets_to_text(items: list[str]) -> str:
    return "\n".join(items)


def build_instructor_app() -> gr.Blocks:
    """Return the Gradio Blocks app for the instructor management page."""

    with gr.Blocks(title="교수자 관리 페이지") as app:
        gr.Markdown("# 🧑‍🏫 교수자 관리 페이지")

        authed = gr.State(value=False)

        # ---------- Login ----------
        with gr.Group(visible=True) as login_group:
            if not admin_enabled():
                gr.Markdown(
                    "⚠️ **관리자 기능이 비활성화되어 있습니다.** "
                    "`.env` 파일에 `INSTRUCTOR_PASSWORD` 를 설정한 뒤 서버를 재시작해주세요."
                )
            else:
                gr.Markdown("관리자 비밀번호를 입력하세요.")
                with gr.Row():
                    pw_in = gr.Textbox(label="비밀번호", type="password", scale=3)
                    login_btn = gr.Button("로그인", variant="primary", scale=1)
                login_msg = gr.Markdown("")

        # ---------- Main panel (hidden until authed) ----------
        with gr.Group(visible=False) as main_panel:
            gr.Markdown("로그인 성공. 아래 탭에서 관리 작업을 진행하세요.")

            with gr.Tabs():
                # ====== Tab 1: 단원 관리 ======
                with gr.Tab("📋 단원 관리"):
                    gr.Markdown("### 등록된 단원")
                    units_df = gr.Dataframe(
                        headers=["파일", "unit_code", "단원명", "페르소나", "학생수"],
                        value=_units_table(),
                        interactive=False,
                        wrap=True,
                    )
                    refresh_units_btn = gr.Button("목록 새로고침")

                    gr.Markdown("### 단원 생성 / 편집")
                    gr.Markdown(
                        "기존 파일명을 입력하면 해당 YAML을 불러와 편집합니다. "
                        "새 단원을 만들려면 `unit_code` 를 새로 지정하고 저장하세요."
                    )

                    with gr.Row():
                        edit_filename_in = gr.Textbox(
                            label="편집할 파일명 (예: photo-01.yaml)", scale=3
                        )
                        edit_load_btn = gr.Button("불러오기", scale=1)

                    unit_code_in = gr.Textbox(label="unit_code (URL에 쓰일 고유값)")
                    subject_in = gr.Textbox(label="과목")
                    unit_name_in = gr.Textbox(label="단원명")
                    target_grade_in = gr.Textbox(
                        label="target_grade_for_teaching (예: 초등 6학년, 비워둬도 됨)"
                    )
                    persona_name_in = gr.Textbox(label="AI 페르소나 이름 (예: 지후)")
                    persona_role_in = gr.Textbox(
                        label="AI 페르소나 역할",
                        value="이해가 부족하고 오개념을 가진 동료 학습자",
                    )
                    instructor_name_in = gr.Textbox(label="담당 교수자 이름")
                    learning_goals_in = gr.Textbox(
                        label="학습 목표 (줄바꿈으로 구분)", lines=4
                    )
                    common_misc_in = gr.Textbox(
                        label="알려진 오개념 (줄바꿈으로 구분)", lines=4
                    )
                    persona_misc_in = gr.Textbox(
                        label="AI가 초기에 품는 오개념 (줄바꿈으로 구분; common_misconceptions의 부분집합 권장)",
                        lines=3,
                    )
                    rubric_in = gr.Textbox(
                        label="루브릭 — 한 줄에 하나: 필수여부 | item_id | 설명 | 키워드(쉼표)",
                        lines=6,
                    )
                    session_minutes_in = gr.Number(
                        label="예상 대화 시간(분)", value=15, precision=0
                    )
                    textbook_in = gr.Textbox(
                        label="교과서 발췌 내용 (선택)", lines=4
                    )

                    with gr.Row():
                        save_unit_btn = gr.Button("저장", variant="primary")
                        delete_unit_btn = gr.Button("삭제", variant="stop")
                    unit_msg = gr.Markdown("")

                # ====== Tab 2: 성찰 질문 ======
                with gr.Tab("❓ 성찰 질문"):
                    gr.Markdown(
                        "### 성찰 질문 편집\n"
                        "JSON 형식으로 편집합니다. "
                        "각 항목은 `id`, `title`, `prompt`, `min_chars` 키를 가집니다. "
                        "`id` 는 DB·리포트에서 매칭에 쓰이니 가능하면 유지하세요."
                    )
                    current = load_reflection_questions()
                    reflection_json = gr.Code(
                        value=json.dumps([asdict(q) for q in current], ensure_ascii=False, indent=2),
                        language="json",
                        label="질문 목록 (JSON)",
                        lines=24,
                    )
                    with gr.Row():
                        save_reflection_btn = gr.Button("저장", variant="primary")
                        reload_reflection_btn = gr.Button("파일에서 다시 불러오기")
                    reflection_msg = gr.Markdown("")

                # ====== Tab 3: 진단 프롬프트 ======
                with gr.Tab("🔬 진단 프롬프트"):
                    gr.Markdown(
                        "### 진단 YAML 편집\n"
                        "각 진단은 Vygotsky·Novak 이론 자료를 참고해 동작합니다. "
                        "프롬프트·루브릭·가중치를 단원 특성에 맞게 조정하세요."
                    )
                    diag_choices = _diagnostics_choices()
                    diag_select = gr.Dropdown(
                        label="진단 선택",
                        choices=diag_choices,
                        value=(diag_choices[0] if diag_choices else None),
                    )
                    diag_yaml_edit = gr.Code(
                        value="", language="yaml", label="진단 YAML 내용", lines=30
                    )
                    with gr.Row():
                        save_diag_btn = gr.Button("저장", variant="primary")
                        reload_diag_btn = gr.Button("다시 불러오기")
                    diag_msg = gr.Markdown("")

                # ====== Tab 4: 참고 자료 ======
                with gr.Tab("📚 참고 자료"):
                    gr.Markdown(
                        "### 이론 참고 자료 관리\n"
                        "업로드한 자료는 진단 YAML의 `reference_materials:` 에 파일명을 추가하면 "
                        "해당 분석 호출에 자동으로 붙여서 Claude에게 전달됩니다. "
                        "지원 포맷: `.md` / `.txt` / `.pdf`."
                    )
                    ref_list_df = gr.Dataframe(
                        headers=["파일명"],
                        value=_reference_list_rows(),
                        interactive=False,
                    )
                    with gr.Row():
                        ref_upload = gr.File(
                            label="자료 업로드 (.md / .txt / .pdf)",
                            file_count="single",
                            file_types=[".md", ".txt", ".pdf"],
                        )
                        ref_dest_name = gr.Textbox(
                            label="저장할 파일명 (비워두면 원본 파일명 사용)"
                        )
                        ref_upload_btn = gr.Button("업로드", variant="primary")

                    with gr.Row():
                        ref_delete_name = gr.Textbox(label="삭제할 파일명")
                        ref_delete_btn = gr.Button("삭제", variant="stop")
                    ref_msg = gr.Markdown("")

                # ====== Tab 5: 세션 조회 ======
                with gr.Tab("📊 세션 조회"):
                    gr.Markdown("### 학생 세션 목록")
                    session_filter_in = gr.Textbox(
                        label="unit_code 로 필터 (비워두면 전체)"
                    )
                    sessions_df = gr.Dataframe(
                        headers=[
                            "session_id",
                            "unit_code",
                            "student_id",
                            "status",
                            "시작",
                            "종료",
                            "턴 수",
                        ],
                        value=_sessions_table(),
                        interactive=False,
                        wrap=True,
                    )
                    refresh_sessions_btn = gr.Button("목록 새로고침")

                    gr.Markdown("### 세션 잠금 해제 (학생 재시도 허용)")
                    with gr.Row():
                        reset_session_id_in = gr.Textbox(
                            label="잠금 해제할 session_id (전체 ID 입력)"
                        )
                        reset_session_btn = gr.Button("잠금 해제")

                    gr.Markdown(
                        "### 분석 다시 실행\n"
                        "완료된 세션의 LLM 분석(오개념 추적·비계 품질·설명 품질·개념도 변화·"
                        "성찰 분석)을 다시 돌립니다. 진단 YAML 을 수정한 뒤 기존 세션에 "
                        "반영하고 싶을 때 사용하세요. 수십 초~1분 정도 걸려요."
                    )
                    with gr.Row():
                        rerun_session_id_in = gr.Textbox(
                            label="재분석할 session_id (전체 ID 입력)"
                        )
                        rerun_btn = gr.Button("분석 재실행", variant="primary")
                    sessions_msg = gr.Markdown("")

                    gr.Markdown(
                        "📄 **PDF 리포트 다운로드는 Phase B5에서 제공됩니다.** "
                        "지금은 분석 JSON 까지 DB에 저장되며, PDF 생성기가 이 데이터를 읽어 렌더링할 예정입니다."
                    )

        # ================ handlers ================

        def on_login(pw: str) -> tuple[Any, Any, Any]:
            if not admin_enabled():
                return False, "⚠️ 비활성화됨. .env 에 INSTRUCTOR_PASSWORD 설정 필요.", gr.update(
                    visible=False
                )
            if not verify_instructor_password(pw):
                return False, "⚠️ 비밀번호가 올바르지 않아요.", gr.update(visible=False)
            return True, "", gr.update(visible=True)

        # -- Tab 1 handlers --

        def on_refresh_units() -> Any:
            return _units_table()

        def on_load_unit(filename: str) -> tuple[Any, ...]:
            filename = (filename or "").strip()
            if not filename:
                return (*(gr.update() for _ in range(11)), "⚠️ 파일명을 입력하세요.")
            try:
                cfg = load_unit_config(Path("configs") / filename)
            except UnitConfigError as exc:
                return (*(gr.update() for _ in range(11)), f"⚠️ 불러오기 실패: {exc}")
            return (
                cfg.unit_code,
                cfg.subject,
                cfg.unit_name,
                cfg.target_grade_for_teaching or "",
                cfg.persona_name,
                cfg.persona_role,
                cfg.instructor_name,
                _bullets_to_text(cfg.learning_goals),
                _bullets_to_text(cfg.common_misconceptions),
                _bullets_to_text(cfg.persona_initial_misconceptions),
                _rubric_to_text(cfg.rubric_items),
                cfg.session_duration_minutes,
                cfg.textbook_content or "",
                f"✅ `{filename}` 불러왔습니다.",
            )

        def on_save_unit(
            unit_code: str,
            subject: str,
            unit_name: str,
            target_grade: str,
            persona_name: str,
            persona_role: str,
            instructor_name: str,
            learning_goals_text: str,
            common_misc_text: str,
            persona_misc_text: str,
            rubric_text: str,
            session_minutes: float,
            textbook: str,
        ) -> tuple[Any, Any]:
            unit_code = (unit_code or "").strip()
            if not unit_code:
                return _units_table(), "⚠️ unit_code 는 필수입니다."

            try:
                rubric_items = _parse_rubric_text(rubric_text)
            except ValueError as exc:
                return _units_table(), f"⚠️ 루브릭 파싱 실패: {exc}"

            try:
                cfg = UnitConfig(
                    unit_code=unit_code,
                    subject=(subject or "").strip() or "과학",
                    unit_name=(unit_name or "").strip() or unit_code,
                    target_grade_for_teaching=(target_grade or "").strip() or None,
                    learning_goals=_bullets_from_text(learning_goals_text),
                    rubric_items=rubric_items,
                    common_misconceptions=_bullets_from_text(common_misc_text),
                    persona_name=(persona_name or "").strip() or "동료",
                    persona_role=(persona_role or "").strip() or "동료 학습자",
                    persona_initial_misconceptions=_bullets_from_text(persona_misc_text),
                    session_duration_minutes=int(session_minutes) if session_minutes else 15,
                    textbook_content=(textbook or "").strip() or None,
                    instructor_name=(instructor_name or "").strip() or "교수자",
                )
            except ValidationError as exc:
                return _units_table(), f"⚠️ 입력 검증 실패:\n{exc}"

            # Preserve existing student_accounts when editing.
            existing_path = Path("configs") / f"{unit_code}.yaml"
            if existing_path.exists():
                try:
                    existing = load_unit_config(existing_path)
                    cfg = cfg.model_copy(update={"student_accounts": existing.student_accounts})
                except UnitConfigError:
                    pass

            path = save_unit_config(cfg)
            return _units_table(), f"✅ 저장 완료: `{path.name}`"

        def on_delete_unit(filename: str) -> tuple[Any, Any]:
            filename = (filename or "").strip()
            if not filename:
                return _units_table(), "⚠️ 삭제할 파일명을 입력하세요."
            delete_unit(filename)
            return _units_table(), f"🗑️ 삭제 완료: `{filename}`"

        # -- Tab 2 handlers --

        def on_save_reflection(text: str) -> str:
            try:
                data = json.loads(text)
                if not isinstance(data, list):
                    raise ValueError("최상위는 JSON 리스트여야 합니다.")
                questions = [
                    ReflectionQuestion(
                        id=str(q["id"]),
                        title=str(q["title"]),
                        prompt=str(q["prompt"]),
                        min_chars=int(q.get("min_chars", 100)),
                    )
                    for q in data
                ]
                save_reflection_questions(questions)
                return f"✅ 저장 완료 ({len(questions)}개 질문)."
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                return f"⚠️ 저장 실패: {exc}"

        def on_reload_reflection() -> str:
            current = load_reflection_questions()
            return json.dumps([asdict(q) for q in current], ensure_ascii=False, indent=2)

        # -- Tab 3 handlers --

        def on_select_diagnostic(filename: str | None) -> str:
            if not filename:
                return ""
            try:
                path = Path("configs/diagnostics") / filename
                return path.read_text(encoding="utf-8")
            except OSError as exc:
                return f"# 불러오기 실패: {exc}"

        def on_save_diagnostic(filename: str | None, content: str) -> str:
            if not filename:
                return "⚠️ 진단을 선택하세요."
            try:
                parsed = yaml.safe_load(content)
                if not isinstance(parsed, dict):
                    return "⚠️ YAML 최상위는 매핑이어야 합니다."
                save_diagnostic(filename, parsed)
                return f"✅ 저장 완료: `{filename}`"
            except yaml.YAMLError as exc:
                return f"⚠️ YAML 파싱 실패: {exc}"

        def on_reload_diagnostic(filename: str | None) -> str:
            return on_select_diagnostic(filename)

        # -- Tab 4 handlers --

        def on_upload_reference(file: Any, dest_name: str) -> tuple[Any, str]:
            if file is None:
                return _reference_list_rows(), "⚠️ 파일을 선택하세요."
            src_path = getattr(file, "name", None) or str(file)
            dest = (dest_name or "").strip() or Path(src_path).name
            try:
                saved = save_reference_upload(src_path, dest)
            except OSError as exc:
                return _reference_list_rows(), f"⚠️ 업로드 실패: {exc}"
            return _reference_list_rows(), f"✅ 업로드 완료: `{saved.name}`"

        def on_delete_reference(filename: str) -> tuple[Any, str]:
            filename = (filename or "").strip()
            if not filename:
                return _reference_list_rows(), "⚠️ 삭제할 파일명을 입력하세요."
            delete_reference(filename)
            return _reference_list_rows(), f"🗑️ 삭제 완료: `{filename}`"

        # -- Tab 5 handlers --

        def on_refresh_sessions(unit_filter: str) -> Any:
            return _sessions_table(unit_filter.strip() or None)

        def on_reset_session(session_id: str) -> tuple[Any, str]:
            session_id = (session_id or "").strip()
            if not session_id:
                return _sessions_table(), "⚠️ session_id 를 입력하세요."
            try:
                reset_session_to_in_progress(session_id)
            except LookupError as exc:
                return _sessions_table(), f"⚠️ 실패: {exc}"
            return _sessions_table(), f"✅ 잠금 해제: `{session_id}`"

        def on_rerun_analysis(session_id: str) -> str:
            session_id = (session_id or "").strip()
            if not session_id:
                return "⚠️ session_id 를 입력하세요."
            try:
                err_count = rerun_analysis(session_id)
            except LookupError as exc:
                return f"⚠️ 실패: {exc}"
            except Exception as exc:  # noqa: BLE001
                return f"⚠️ 재분석 중 오류: {exc}"
            if err_count == 0:
                return f"✅ `{session_id}` 재분석 완료. 모든 모듈 정상."
            return (
                f"⚠️ `{session_id}` 재분석 완료. 일부 모듈에서 {err_count}건의 오류 발생 — "
                "세션 DB의 analysis_json 을 확인하세요."
            )

        # ================ wiring ================

        if admin_enabled():
            login_btn.click(
                on_login, inputs=[pw_in], outputs=[authed, login_msg, main_panel]
            )

        # Tab 1
        refresh_units_btn.click(on_refresh_units, inputs=None, outputs=units_df)
        edit_load_btn.click(
            on_load_unit,
            inputs=[edit_filename_in],
            outputs=[
                unit_code_in,
                subject_in,
                unit_name_in,
                target_grade_in,
                persona_name_in,
                persona_role_in,
                instructor_name_in,
                learning_goals_in,
                common_misc_in,
                persona_misc_in,
                rubric_in,
                session_minutes_in,
                textbook_in,
                unit_msg,
            ],
        )
        save_unit_btn.click(
            on_save_unit,
            inputs=[
                unit_code_in,
                subject_in,
                unit_name_in,
                target_grade_in,
                persona_name_in,
                persona_role_in,
                instructor_name_in,
                learning_goals_in,
                common_misc_in,
                persona_misc_in,
                rubric_in,
                session_minutes_in,
                textbook_in,
            ],
            outputs=[units_df, unit_msg],
        )
        delete_unit_btn.click(
            on_delete_unit, inputs=[edit_filename_in], outputs=[units_df, unit_msg]
        )

        # Tab 2
        save_reflection_btn.click(
            on_save_reflection, inputs=[reflection_json], outputs=[reflection_msg]
        )
        reload_reflection_btn.click(
            on_reload_reflection, inputs=None, outputs=[reflection_json]
        )

        # Tab 3
        diag_select.change(on_select_diagnostic, inputs=[diag_select], outputs=[diag_yaml_edit])
        save_diag_btn.click(
            on_save_diagnostic,
            inputs=[diag_select, diag_yaml_edit],
            outputs=[diag_msg],
        )
        reload_diag_btn.click(
            on_reload_diagnostic, inputs=[diag_select], outputs=[diag_yaml_edit]
        )

        # Tab 4
        ref_upload_btn.click(
            on_upload_reference,
            inputs=[ref_upload, ref_dest_name],
            outputs=[ref_list_df, ref_msg],
        )
        ref_delete_btn.click(
            on_delete_reference,
            inputs=[ref_delete_name],
            outputs=[ref_list_df, ref_msg],
        )

        # Tab 5
        refresh_sessions_btn.click(
            on_refresh_sessions, inputs=[session_filter_in], outputs=[sessions_df]
        )
        reset_session_btn.click(
            on_reset_session,
            inputs=[reset_session_id_in],
            outputs=[sessions_df, sessions_msg],
        )
        rerun_btn.click(on_rerun_analysis, inputs=[rerun_session_id_in], outputs=[sessions_msg])

    return app
