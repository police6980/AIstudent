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
from src.services.claude_service import ClaudeServiceError
from src.services.instructor_service import (
    admin_enabled,
    delete_reference,
    delete_unit,
    get_api_key_status,
    get_report_paths_for_session,
    list_sessions,
    list_units,
    rerun_analysis,
    reset_session_to_in_progress,
    save_reference_upload,
    save_unit_config,
    set_runtime_api_key,
    verify_instructor_password,
)
from src.services.unit_auto_generator import (
    auto_generate_unit_from_text,
    fill_student_accounts,
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

            # ====== API 키 상태 + 런타임 업데이트 ======
            with gr.Accordion("🔑 API 키 설정 (이 세션에만 유효)", open=False):
                gr.Markdown(
                    "`ANTHROPIC_API_KEY` 가 비어있거나 바꾸고 싶을 때 여기서 입력할 수 있습니다.\n"
                    "- **저장되지 않습니다** — 앱을 껐다 켜면 `.env` 의 값으로 돌아갑니다.\n"
                    "- 유출 위험을 줄이려면 `.env` 에 영구 저장하는 편이 안전합니다."
                )
                api_key_status = gr.Markdown("")
                with gr.Row():
                    api_key_in = gr.Textbox(
                        label="새 API 키 (sk-ant-api03-...)",
                        type="password",
                        scale=4,
                    )
                    api_key_apply_btn = gr.Button("적용", variant="primary", scale=1)
                api_key_msg = gr.Markdown("")

            with gr.Tabs():
                # ====== Tab 0: 간편 단원 생성 (new default) ======
                with gr.Tab("✨ 간편 단원 생성"):
                    gr.Markdown(
                        "### 교안·교재 내용을 붙여넣기만 하면 단원 설정을 **AI 가 자동으로 생성**합니다.\n"
                        "그 다음 버튼 한 번으로 학생 계정 30개까지 바로 만들어 드려요."
                    )

                    with gr.Row():
                        auto_unit_code_in = gr.Textbox(
                            label="단원 코드 (URL에 쓸 짧은 이름)",
                            placeholder="예: photo-01, solution-01",
                            scale=2,
                        )
                        auto_unit_name_in = gr.Textbox(
                            label="단원명",
                            placeholder="예: 광합성, 용액과 용질",
                            scale=2,
                        )
                        auto_target_grade_in = gr.Textbox(
                            label="대상 학년",
                            placeholder="예: 초등 6학년",
                            scale=2,
                        )

                    auto_persona_in = gr.Textbox(
                        label="AI 동료 이름 (비워두면 '지후')",
                        placeholder="지후",
                    )

                    auto_content_in = gr.Textbox(
                        label="📄 교안·교재·메모 (학생 대화 중에도 AI 가 참고)",
                        placeholder=(
                            "여기에 수업 계획, 교과서 발췌, 핵심 개념, 관련 자료 등을 붙여넣으세요.\n"
                            "• AI 가 학생과 대화하는 중에 **보충 자료로 참고** 합니다.\n"
                            "• 'AI 로 자동 생성' 버튼을 누르면 이 내용에서 학습 목표·루브릭·오개념을 추출합니다.\n"
                            "  (자동 생성 쓰기 싫으면 아래 미리보기 필드들을 직접 채우고 바로 저장해도 됨)\n"
                            "\n예)\n"
                            "광합성은 식물이 빛, 물, 이산화탄소를 이용해 포도당과 산소를 만드는 과정이다. "
                            "주로 엽록체에서 일어나며, 초등학생들이 자주 가지는 오개념으로는..."
                        ),
                        lines=10,
                    )

                    with gr.Row():
                        auto_generate_btn = gr.Button(
                            "🤖 AI로 학습목표·루브릭·오개념 자동 추출 (선택)",
                            variant="secondary",
                            scale=2,
                        )
                        auto_save_btn = gr.Button(
                            "💾 저장 + 학생 링크 만들기",
                            variant="primary",
                            scale=2,
                        )

                    auto_status = gr.Markdown(
                        "ℹ️ 본 시스템은 **학번 + 이름** 만 입력하면 로그인되므로, "
                        "학생 계정을 미리 만들 필요가 없습니다. 저장하면 바로 학생 링크가 생성됩니다."
                    )

                    gr.Markdown(
                        "### ✍️ 단원 세부 설정 — 직접 입력하거나 AI 로 채운 뒤 수정"
                    )
                    auto_preview_subject = gr.Textbox(
                        label="과목", value="과학", interactive=True
                    )
                    auto_preview_goals = gr.Textbox(
                        label="학습 목표 (한 줄에 하나)",
                        placeholder="예)\n광합성의 조건 (빛, 물, 이산화탄소)\n광합성의 산물 (포도당, 산소)",
                        lines=5,
                        interactive=True,
                    )
                    auto_preview_rubric = gr.Textbox(
                        label="루브릭 (JSON — AI 생성 시 자동 채워짐. 직접 편집도 가능)",
                        placeholder='[\n  {"item_id": "r_light", "description": "빛이 조건", "keywords": ["빛", "햇빛"], "required": true}\n]',
                        lines=8,
                        interactive=True,
                    )
                    auto_preview_miscons = gr.Textbox(
                        label="알려진 오개념 (한 줄에 하나)",
                        placeholder="예)\n식물은 흙에서 양분을 흡수해 자란다\n광합성은 낮에만 일어난다",
                        lines=5,
                        interactive=True,
                    )
                    auto_preview_ai_miscons = gr.Textbox(
                        label="AI 페르소나가 처음에 품고 있을 오개념 (1~2개, 한 줄에 하나)",
                        placeholder="예)\n식물은 흙에서 양분을 흡수해 자란다",
                        lines=3,
                        interactive=True,
                    )

                    gr.Markdown("### 🔗 학생에게 배포할 링크")
                    auto_student_link_out = gr.Textbox(
                        label="학생 접속 URL (저장 후 여기에 채워짐)",
                        interactive=False,
                    )
                    gr.Markdown(
                        "💡 학생은 이 링크만 있으면 됩니다.\n"
                        "- 학번 + 이름 입력으로 로그인 (비밀번호 불필요)\n"
                        "- 같은 링크로 **여러 학생 동시 접속** 가능\n"
                        "- 활동 끝나면 학생이 PDF 다운로드 + 교수님 `data\\reports\\` 폴더에도 자동 저장"
                    )

                # ====== Tab 1: 단원 관리 (상세/고급) ======
                with gr.Tab("📋 단원 관리 (고급)"):
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

                    gr.Markdown("### PDF 다운로드")
                    with gr.Row():
                        download_session_id_in = gr.Textbox(
                            label="다운로드할 session_id (전체 ID)"
                        )
                        download_btn = gr.Button("불러오기")
                    with gr.Row():
                        summary_file_inst = gr.File(label="요약", interactive=False)
                        detail_file_inst = gr.File(label="상세", interactive=False)

        # ================ handlers ================

        def _api_key_status_text() -> str:
            ok, preview = get_api_key_status()
            if ok:
                return f"✅ 현재 사용 중: `{preview}`"
            return "⚠️ **API 키가 설정되지 않았어요.** AI 호출이 실패합니다. 아래에서 입력해주세요."

        def on_login(pw: str) -> tuple[Any, Any, Any, Any]:
            if not admin_enabled():
                return (
                    False,
                    "⚠️ 비활성화됨. .env 에 INSTRUCTOR_PASSWORD 설정 필요.",
                    gr.update(visible=False),
                    _api_key_status_text(),
                )
            if not verify_instructor_password(pw):
                return (
                    False,
                    "⚠️ 비밀번호가 올바르지 않아요.",
                    gr.update(visible=False),
                    _api_key_status_text(),
                )
            return True, "", gr.update(visible=True), _api_key_status_text()

        def on_apply_api_key(new_key: str) -> tuple[str, str, str]:
            ok, message = set_runtime_api_key(new_key)
            status = _api_key_status_text()
            if ok:
                return status, f"✅ {message}", ""  # clear the input
            return status, f"⚠️ {message}", new_key

        # ----- Auto-generate unit (Tab 0) -----

        def _rubric_to_preview_json(rubric_items: list) -> str:
            import json as _json

            simple = [
                {
                    "item_id": r.item_id,
                    "description": r.description,
                    "keywords": list(r.keywords),
                    "required": bool(r.required),
                }
                for r in rubric_items
            ]
            return _json.dumps(simple, ensure_ascii=False, indent=2)

        def on_auto_generate(
            unit_code: str,
            unit_name: str,
            target_grade: str,
            persona_name: str,
            content: str,
        ) -> tuple[str, str, str, str, str, str]:
            """Call Claude to draft the unit, fill the preview fields."""

            unit_code = (unit_code or "").strip()
            unit_name = (unit_name or "").strip()
            if not unit_code or not unit_name:
                return (
                    "⚠️ 단원 코드와 단원명을 먼저 입력하세요.",
                    "", "", "", "", "",
                )
            if not (content or "").strip():
                return (
                    "⚠️ 교안/교재 내용을 붙여넣으세요.",
                    "", "", "", "", "",
                )
            try:
                unit = auto_generate_unit_from_text(
                    unit_code=unit_code,
                    unit_name=unit_name,
                    target_grade=target_grade or "",
                    raw_content=content,
                    persona_name=persona_name or "지후",
                )
            except ClaudeServiceError as exc:
                return (f"⚠️ Claude 호출 실패: {exc}", "", "", "", "", "")
            except ValueError as exc:
                return (f"⚠️ {exc}", "", "", "", "", "")
            except Exception as exc:  # noqa: BLE001
                logger.exception("auto-generate failed")
                return (f"⚠️ 생성 중 오류: {exc}", "", "", "", "", "")

            goals_text = "\n".join(unit.learning_goals)
            rubric_text = _rubric_to_preview_json(unit.rubric_items)
            miscon_text = "\n".join(unit.common_misconceptions)
            ai_miscon_text = "\n".join(unit.persona_initial_misconceptions)

            return (
                f"✅ AI가 {len(unit.rubric_items)}개 루브릭·"
                f"{len(unit.common_misconceptions)}개 오개념을 추출했어요. "
                "필요하면 아래 미리보기에서 편집한 뒤 **💾 저장** 을 누르세요.",
                unit.subject,
                goals_text,
                rubric_text,
                miscon_text,
                ai_miscon_text,
            )

        def _parse_preview_to_unit(
            unit_code: str,
            unit_name: str,
            target_grade: str,
            persona_name: str,
            subject: str,
            goals_text: str,
            rubric_json: str,
            miscon_text: str,
            ai_miscon_text: str,
        ):
            """Re-build a UnitConfig from the possibly-edited preview fields."""

            import json as _json

            from src.models.schemas import RubricItem, UnitConfig

            goals = [g.strip() for g in (goals_text or "").splitlines() if g.strip()]
            miscons = [m.strip() for m in (miscon_text or "").splitlines() if m.strip()]
            ai_miscons = [
                m.strip() for m in (ai_miscon_text or "").splitlines() if m.strip()
            ]
            rubric_items: list[RubricItem] = []
            if (rubric_json or "").strip():
                try:
                    for i, item in enumerate(_json.loads(rubric_json)):
                        rubric_items.append(
                            RubricItem(
                                item_id=str(item.get("item_id") or f"r_{i+1}").strip(),
                                description=str(item.get("description") or "").strip(),
                                keywords=[
                                    str(k).strip()
                                    for k in (item.get("keywords") or [])
                                    if str(k).strip()
                                ],
                                required=bool(item.get("required", True)),
                            )
                        )
                except Exception as exc:  # noqa: BLE001
                    raise ValueError(f"루브릭 JSON 오류: {exc}") from exc

            return UnitConfig(
                unit_code=unit_code.strip(),
                subject=(subject or "과학").strip(),
                unit_name=unit_name.strip(),
                target_grade_for_teaching=(target_grade or "").strip() or None,
                learning_goals=goals,
                rubric_items=rubric_items,
                common_misconceptions=miscons,
                persona_name=(persona_name or "지후").strip() or "지후",
                persona_role="같은 단원을 공부하는 교대 동료 학생",
                persona_initial_misconceptions=ai_miscons,
                hint_max_count=3,
                session_duration_minutes=15,
                instructor_name="교수",
                student_accounts=[],
            )

        def on_auto_save(
            unit_code: str,
            unit_name: str,
            target_grade: str,
            persona_name: str,
            subject: str,
            goals_text: str,
            rubric_json: str,
            miscon_text: str,
            ai_miscon_text: str,
            textbook_text: str,
        ) -> tuple[str, str]:
            """Save the unit YAML in open login mode (no preset accounts)."""

            try:
                unit = _parse_preview_to_unit(
                    unit_code=unit_code,
                    unit_name=unit_name,
                    target_grade=target_grade,
                    persona_name=persona_name,
                    subject=subject,
                    goals_text=goals_text,
                    rubric_json=rubric_json,
                    miscon_text=miscon_text,
                    ai_miscon_text=ai_miscon_text,
                )
            except Exception as exc:  # noqa: BLE001
                return f"⚠️ 저장 실패: {exc}", ""

            # Attach textbook content + set open login mode
            if textbook_text and textbook_text.strip():
                unit.textbook_content = textbook_text.strip()
            unit.student_login_mode = "open"

            try:
                save_unit_config(unit, configs_dir=CONFIGS_DIR)
            except Exception as exc:  # noqa: BLE001
                return f"⚠️ YAML 저장 실패: {exc}", ""

            link_hint = (
                f"<공개URL>/?unit={unit.unit_code}\n"
                "('3_run_app.bat' 실행 시 터미널의 'Running on public URL:' 주소를 앞에 붙이세요)"
            )

            return (
                f"✅ **{unit.unit_code}** 저장 완료.\n"
                f"학생은 이 링크로 접속 → 학번+이름 입력만 하면 바로 시작.\n"
                f"단원 YAML: `configs/{unit.unit_code}.yaml`",
                link_hint,
            )

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

        def on_download_reports(session_id: str) -> tuple[Any, Any, str]:
            session_id = (session_id or "").strip()
            if not session_id:
                return None, None, "⚠️ session_id 를 입력하세요."
            summary, detail = get_report_paths_for_session(session_id)
            if not summary:
                return (
                    None,
                    None,
                    "⚠️ 해당 세션의 PDF 가 아직 없거나 세션을 찾을 수 없어요. "
                    "완료된 세션인지 확인하거나 '분석 재실행' 을 먼저 눌러주세요.",
                )
            return summary, detail, f"✅ `{session_id}` 리포트 2건 로드됨."

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
                on_login,
                inputs=[pw_in],
                outputs=[authed, login_msg, main_panel, api_key_status],
            )

        api_key_apply_btn.click(
            on_apply_api_key,
            inputs=[api_key_in],
            outputs=[api_key_status, api_key_msg, api_key_in],
        )

        # ---- Tab 0 wiring ----
        auto_generate_btn.click(
            on_auto_generate,
            inputs=[
                auto_unit_code_in,
                auto_unit_name_in,
                auto_target_grade_in,
                auto_persona_in,
                auto_content_in,
            ],
            outputs=[
                auto_status,
                auto_preview_subject,
                auto_preview_goals,
                auto_preview_rubric,
                auto_preview_miscons,
                auto_preview_ai_miscons,
            ],
        )

        auto_save_btn.click(
            on_auto_save,
            inputs=[
                auto_unit_code_in,
                auto_unit_name_in,
                auto_target_grade_in,
                auto_persona_in,
                auto_preview_subject,
                auto_preview_goals,
                auto_preview_rubric,
                auto_preview_miscons,
                auto_preview_ai_miscons,
                auto_content_in,
            ],
            outputs=[auto_status, auto_student_link_out],
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
        download_btn.click(
            on_download_reports,
            inputs=[download_session_id_in],
            outputs=[summary_file_inst, detail_file_inst, sessions_msg],
        )

    return app
