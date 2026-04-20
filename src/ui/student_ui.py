"""Gradio student UI — multi-step flow.

Steps (gated by SessionStep):
    1. LOGIN       — ?unit=xxx + ID + 5-char password
    2. PRE_MAP     — build initial Novak concept map
    3. DIALOGUE    — chat with the misconception-holding peer AI
    4. POST_MAP    — build the post-learning concept map
    5. REFLECTION  — answer 5 reflection questions (≥100 chars each)
    6. COMPLETED   — summary screen (PDF download arrives in Phase B5)

Re-login jumps to whichever step the session is currently on; completed
sessions are locked out.
"""

from __future__ import annotations

import logging
from typing import Any

import gradio as gr

from src.models.enums import SessionStep, Speaker
from src.models.schemas import Turn
from src.services.diagnostics import load_reflection_questions
from src.services.session_manager import (
    AuthenticationError,
    SessionLockedError,
    SessionManager,
    StepViolationError,
)
from src.ui.concept_map_ui import (
    ConceptMapParseError,
    build_concept_map_from_inputs,
    build_concept_map_input_block,
)

logger = logging.getLogger(__name__)

# Visibility helpers — one per pane. True = show that pane only.
PANES = ("login", "pre_map", "dialogue", "post_map", "reflection", "completed")


def _visibility(active: str) -> dict[str, Any]:
    return {name: gr.update(visible=(name == active)) for name in PANES}


def _step_to_pane(step: SessionStep) -> str:
    return {
        SessionStep.PRE_MAP: "pre_map",
        SessionStep.DIALOGUE: "dialogue",
        SessionStep.POST_MAP: "post_map",
        SessionStep.REFLECTION: "reflection",
        SessionStep.COMPLETED: "completed",
    }[step]


def _render_history(turns: list[Turn]) -> list[list[str | None]]:
    pairs: list[list[str | None]] = []
    for t in turns:
        if t.speaker == Speaker.STUDENT:
            pairs.append([t.content, None])
        else:
            if pairs and pairs[-1][1] is None:
                pairs[-1][1] = t.content
            else:
                pairs.append([None, t.content])
    return pairs


def _parse_unit_code(request: gr.Request | None) -> str:
    if request is None:
        return ""
    try:
        return (request.query_params.get("unit") or "").strip()
    except Exception:  # pragma: no cover - defensive
        return ""


def build_student_app(manager: SessionManager | None = None) -> gr.Blocks:
    mgr = manager or SessionManager()
    questions = load_reflection_questions()

    with gr.Blocks(title="예비교사 과학 설명 훈련") as app:
        gr.Markdown(
            "## 🧠 예비교사 과학 설명 훈련\n"
            "동료 학습자(AI)에게 오늘 배운 단원을 설명하며, 본인의 이해를 깊게 하는 활동입니다. "
            "**초기 개념도 → 대화 → 사후 개념도 → 성찰** 순서로 진행되며, "
            "모든 단계를 마치면 리포트가 생성됩니다."
        )

        session_state = gr.State(value=None)
        unit_code_state = gr.State(value="")

        # =========================================================================
        # Pane 1: LOGIN
        # =========================================================================
        with gr.Group(visible=True) as login_pane:
            gr.Markdown("### 1단계. 로그인")
            unit_display = gr.Markdown("*단원 정보를 확인하는 중...*")
            with gr.Row():
                sid_in = gr.Textbox(label="학생 ID", placeholder="예: s01", scale=2)
                pw_in = gr.Textbox(
                    label="비밀번호(5자리)", placeholder="5자리", type="password", scale=2
                )
                login_btn = gr.Button("시작하기", variant="primary", scale=1)
            login_msg = gr.Markdown("")

        # =========================================================================
        # Pane 2: PRE_MAP
        # =========================================================================
        with gr.Group(visible=False) as pre_map_pane:
            gr.Markdown("### 2단계. 초기 개념도 작성")
            pre_map_block = build_concept_map_input_block(
                title="🗺️ 오늘 단원에 대한 현재 내 개념도",
                description_md=(
                    "오늘 공부한 단원에 대해 **지금 머릿속에 있는 개념들**을 구조로 옮겨보세요.\n"
                    "- **개념**은 명사로 (예: 광합성, 빛, 엽록체)\n"
                    "- **명제**는 두 개념을 이을 때 `시작 | 연결어 | 끝` 형식 "
                    "(예: `광합성 | 의 조건은 | 빛`)\n"
                    "- **교차연결**은 서로 다른 가지를 잇는 특별한 연결\n"
                    "- **예시**는 개념을 뒷받침하는 구체 사례\n\n"
                    "막막하다면 먼저 개념만 쭉 적고, 명제는 그다음에 채워도 됩니다."
                ),
                submit_label="제출 → 대화 시작",
                state_prefix="pre",
            )

        # =========================================================================
        # Pane 3: DIALOGUE
        # =========================================================================
        with gr.Group(visible=False) as dialogue_pane:
            gr.Markdown("### 3단계. 동료 학습자와의 대화")
            dialogue_status = gr.Markdown("")
            dialogue_chatbot = gr.Chatbot(label="대화", height=440)
            with gr.Row():
                msg_in = gr.Textbox(
                    label="내 설명 입력",
                    placeholder="AI에게 설명하고 싶은 내용을 적고 Enter 또는 보내기를 눌러요.",
                    lines=2,
                    scale=5,
                )
                send_btn = gr.Button("보내기", variant="primary", scale=1)
            with gr.Row():
                end_dialogue_btn = gr.Button("대화 종료 → 사후 개념도로", variant="stop")

        # =========================================================================
        # Pane 4: POST_MAP
        # =========================================================================
        with gr.Group(visible=False) as post_map_pane:
            gr.Markdown("### 4단계. 사후 개념도 작성")
            gr.Markdown(
                "대화를 통해 이해가 달라졌거나 정리된 부분을 반영해서 **다시 개념도를** 작성해주세요. "
                "초기 개념도는 비교를 위해 의도적으로 보여드리지 않습니다."
            )
            post_map_block = build_concept_map_input_block(
                title="🗺️ 대화 후의 내 개념도",
                description_md=(
                    "지금 머릿속에 있는 개념들을 다시 정리해서 써주세요. "
                    "초기 개념도에서 추가된 것, 바뀐 것, 새로 생긴 연결을 반영하면 좋아요."
                ),
                submit_label="제출 → 성찰 질문으로",
                state_prefix="post",
            )

        # =========================================================================
        # Pane 5: REFLECTION
        # =========================================================================
        with gr.Group(visible=False) as reflection_pane:
            gr.Markdown("### 5단계. 성찰 질문")
            gr.Markdown(
                "아래 질문에 각각 **{min_chars}자 이상** 답변해주세요. "
                "모두 완료되면 '제출' 버튼이 활성화됩니다.".format(
                    min_chars=questions[0].min_chars if questions else 100
                )
            )
            reflection_inputs: dict[str, gr.Textbox] = {}
            reflection_counters: dict[str, gr.Markdown] = {}
            for q in questions:
                gr.Markdown(f"**{q.title}**\n\n{q.prompt}")
                box = gr.Textbox(
                    label=f"{q.title} (최소 {q.min_chars}자)",
                    lines=5,
                    placeholder="이곳에 답변을 작성하세요...",
                )
                counter = gr.Markdown(f"0 / {q.min_chars}자")

                def _make_counter(min_chars: int):
                    def _update(text: str) -> str:
                        n = len((text or "").strip())
                        ok = "✅" if n >= min_chars else "⏳"
                        return f"{ok} {n} / {min_chars}자"

                    return _update

                box.change(_make_counter(q.min_chars), inputs=[box], outputs=[counter])
                reflection_inputs[q.id] = box
                reflection_counters[q.id] = counter

            submit_reflection_btn = gr.Button(
                "성찰 제출하고 세션 완료하기", variant="primary"
            )
            reflection_msg = gr.Markdown("")

        # =========================================================================
        # Pane 6: COMPLETED
        # =========================================================================
        with gr.Group(visible=False) as completed_pane:
            gr.Markdown("## ✅ 모든 단계를 완료했어요")
            completed_info = gr.Markdown("")
            gr.Markdown(
                "📄 **리포트 파일 2개를 내려받아 교수자에게 제출하세요.**\n"
                "- `요약.pdf` — 핵심 개요 (2페이지)\n"
                "- `상세.pdf` — 대화 전사·개념도 변화·분석 전체 (여러 페이지)\n\n"
                "분석 생성에 수십 초~1분이 걸릴 수 있어요. "
                "버튼이 보이지 않으면 '다시 불러오기' 를 눌러주세요."
            )
            with gr.Row():
                summary_file = gr.File(label="요약 리포트", interactive=False)
                detail_file = gr.File(label="상세 리포트", interactive=False)
            refresh_reports_btn = gr.Button("🔄 리포트 다시 불러오기")

        # ========================= handlers =================================

        panes = {
            "login": login_pane,
            "pre_map": pre_map_pane,
            "dialogue": dialogue_pane,
            "post_map": post_map_pane,
            "reflection": reflection_pane,
            "completed": completed_pane,
        }

        def _show(pane_name: str) -> list[Any]:
            """Return a list of gr.update() for the 6 panes in PANES order."""

            return [gr.update(visible=(name == pane_name)) for name in PANES]

        def on_load(request: gr.Request) -> tuple[Any, str]:
            code = _parse_unit_code(request)
            if not code:
                return (
                    "⚠️ URL에 단원 정보가 없어요. 교수자가 알려준 링크(예: `?unit=photo-01`)로 "
                    "다시 접속해주세요.",
                    "",
                )
            try:
                mgr.load_unit(code)
            except AuthenticationError as exc:
                return f"⚠️ {exc}", ""
            return f"**단원 코드:** `{code}`\n\n학생 ID와 비밀번호를 입력하세요.", code

        def on_login(
            unit_code: str, sid: str, pw: str
        ) -> tuple[Any, Any, Any, Any, Any, Any, Any, Any, Any, Any]:
            if not unit_code:
                return (
                    *_show("login"),
                    None,
                    "⚠️ 단원 코드가 없어요. 교수자에게 받은 링크로 접속해주세요.",
                    "",
                    [],
                )
            try:
                result = mgr.login(unit_code, sid, pw)
            except AuthenticationError as exc:
                return (*_show("login"), None, f"⚠️ {exc}", "", [])
            except SessionLockedError as exc:
                return (*_show("login"), None, f"🔒 {exc}", "", [])

            pane = _step_to_pane(result.current_step)
            status = (
                f"**{result.unit_config.persona_name}** 와 대화 중 · "
                f"단원: {result.unit_config.unit_name} · ID: `{sid}`"
            )
            return (
                *_show(pane),
                result.session_id,
                "",
                status,
                _render_history(result.turns),
            )

        # ---- PRE_MAP submit ----

        def on_submit_pre_map(
            session_id: str | None,
            concepts_text: str,
            props_text: str,
            cross_text: str,
            examples_text: str,
        ) -> tuple[Any, ...]:
            if not session_id:
                return (*_show("login"), "⚠️ 로그인 먼저 하세요.", "", [])
            try:
                parsed = build_concept_map_from_inputs(
                    concepts_text, props_text, cross_text, examples_text
                )
            except ConceptMapParseError as exc:
                return (*_show("pre_map"), f"⚠️ {exc}", "", [])

            try:
                result = mgr.submit_pre_concept_map(session_id, parsed.concept_map)
            except (SessionLockedError, StepViolationError, LookupError) as exc:
                return (*_show("pre_map"), f"⚠️ {exc}", "", [])

            turns = mgr.get_turns(session_id)
            status = "AI 동료와 대화 중 — 설명을 시작해보세요."
            if result.diagnosis and result.diagnosis.level != "unknown":
                status += f"  (진단: {result.diagnosis.level})"
            return (*_show("dialogue"), "", status, _render_history(turns))

        # ---- DIALOGUE send ----

        def on_send(session_id: str | None, user_text: str) -> tuple[Any, Any, Any]:
            user_text = (user_text or "").strip()
            if not session_id:
                return gr.update(), "⚠️ 먼저 로그인하세요.", ""
            if not user_text:
                return gr.update(), gr.update(), ""
            try:
                mgr.submit_student_turn(session_id, user_text)
            except SessionLockedError as exc:
                return gr.update(), f"🔒 {exc}", user_text
            except (ValueError, LookupError, StepViolationError) as exc:
                return gr.update(), f"⚠️ 전송 실패: {exc}", user_text
            return _render_history(mgr.get_turns(session_id)), gr.update(), ""

        # ---- End dialogue → POST_MAP ----

        def on_end_dialogue(session_id: str | None) -> tuple[Any, ...]:
            if not session_id:
                return (*_show("login"), "⚠️ 로그인 먼저 하세요.")
            try:
                mgr.end_dialogue(session_id)
            except (SessionLockedError, StepViolationError, LookupError) as exc:
                return (*_show("dialogue"), f"⚠️ {exc}")
            return (*_show("post_map"), "")

        # ---- POST_MAP submit → REFLECTION ----

        def on_submit_post_map(
            session_id: str | None,
            concepts_text: str,
            props_text: str,
            cross_text: str,
            examples_text: str,
        ) -> tuple[Any, ...]:
            if not session_id:
                return (*_show("login"), "")
            try:
                parsed = build_concept_map_from_inputs(
                    concepts_text, props_text, cross_text, examples_text
                )
            except ConceptMapParseError as exc:
                return (*_show("post_map"), f"⚠️ {exc}")
            try:
                mgr.submit_post_concept_map(session_id, parsed.concept_map)
            except (SessionLockedError, StepViolationError, LookupError) as exc:
                return (*_show("post_map"), f"⚠️ {exc}")
            return (*_show("reflection"), "")

        # ---- REFLECTION submit → COMPLETED ----

        question_ids = [q.id for q in questions]

        def _fetch_report_files(session_id: str | None) -> tuple[Any, Any]:
            if not session_id:
                return None, None
            paths = mgr.get_report_paths(session_id)
            if paths is None:
                return None, None
            return str(paths.summary), str(paths.detail)

        def on_submit_reflection(session_id: str | None, *answers: str) -> tuple[Any, ...]:
            if not session_id:
                return (*_show("login"), "⚠️ 로그인 먼저 하세요.", "", None, None)
            ans_map = dict(zip(question_ids, answers))
            try:
                mgr.submit_reflection_answers(session_id, ans_map)
            except (SessionLockedError, StepViolationError, LookupError) as exc:
                return (*_show("reflection"), f"⚠️ {exc}", "", None, None)
            except ValueError as exc:
                return (*_show("reflection"), f"⚠️ 제출 실패:\n{exc}", "", None, None)
            info = f"세션 ID: `{session_id}`"
            summary_path, detail_path = _fetch_report_files(session_id)
            return (*_show("completed"), "", info, summary_path, detail_path)

        def on_refresh_reports(session_id: str | None) -> tuple[Any, Any]:
            summary_path, detail_path = _fetch_report_files(session_id)
            return summary_path, detail_path

        # ============================ wiring ================================

        app.load(on_load, inputs=None, outputs=[unit_display, unit_code_state])

        login_btn.click(
            on_login,
            inputs=[unit_code_state, sid_in, pw_in],
            outputs=[
                login_pane,
                pre_map_pane,
                dialogue_pane,
                post_map_pane,
                reflection_pane,
                completed_pane,
                session_state,
                login_msg,
                dialogue_status,
                dialogue_chatbot,
            ],
        )

        pre_map_block["submit_btn"].click(
            on_submit_pre_map,
            inputs=[
                session_state,
                pre_map_block["concepts_in"],
                pre_map_block["propositions_in"],
                pre_map_block["cross_links_in"],
                pre_map_block["examples_in"],
            ],
            outputs=[
                login_pane,
                pre_map_pane,
                dialogue_pane,
                post_map_pane,
                reflection_pane,
                completed_pane,
                pre_map_block["warnings_md"],
                dialogue_status,
                dialogue_chatbot,
            ],
        )

        send_btn.click(
            on_send,
            inputs=[session_state, msg_in],
            outputs=[dialogue_chatbot, dialogue_status, msg_in],
        )
        msg_in.submit(
            on_send,
            inputs=[session_state, msg_in],
            outputs=[dialogue_chatbot, dialogue_status, msg_in],
        )

        end_dialogue_btn.click(
            on_end_dialogue,
            inputs=[session_state],
            outputs=[
                login_pane,
                pre_map_pane,
                dialogue_pane,
                post_map_pane,
                reflection_pane,
                completed_pane,
                dialogue_status,
            ],
        )

        post_map_block["submit_btn"].click(
            on_submit_post_map,
            inputs=[
                session_state,
                post_map_block["concepts_in"],
                post_map_block["propositions_in"],
                post_map_block["cross_links_in"],
                post_map_block["examples_in"],
            ],
            outputs=[
                login_pane,
                pre_map_pane,
                dialogue_pane,
                post_map_pane,
                reflection_pane,
                completed_pane,
                post_map_block["warnings_md"],
            ],
        )

        submit_reflection_btn.click(
            on_submit_reflection,
            inputs=[session_state] + [reflection_inputs[qid] for qid in question_ids],
            outputs=[
                login_pane,
                pre_map_pane,
                dialogue_pane,
                post_map_pane,
                reflection_pane,
                completed_pane,
                reflection_msg,
                completed_info,
                summary_file,
                detail_file,
            ],
        )

        refresh_reports_btn.click(
            on_refresh_reports,
            inputs=[session_state],
            outputs=[summary_file, detail_file],
        )

    return app
