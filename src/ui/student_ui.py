"""Gradio student UI: URL-unit routing, ID+password login, text chat, session completion.

URL example:  http://<host>/?unit=photo-01
Student flow: open URL → enter student_id + password → chat → complete → (Phase B: download PDFs)
"""

from __future__ import annotations

from typing import Any

import gradio as gr

from src.models.enums import Speaker
from src.models.schemas import Turn
from src.services.session_manager import (
    AuthenticationError,
    SessionLockedError,
    SessionManager,
)


def _render_history(turns: list[Turn]) -> list[list[str | None]]:
    """Format Turn list into Gradio Chatbot pairs: [student, ai]."""

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
    """Extract `?unit=...` from the Gradio request URL."""

    if request is None:
        return ""
    try:
        return (request.query_params.get("unit") or "").strip()
    except Exception:  # pragma: no cover - defensive
        return ""


def build_student_app(manager: SessionManager | None = None) -> gr.Blocks:
    """Return a Gradio Blocks app for the preservice-teacher chat."""

    mgr = manager or SessionManager()

    with gr.Blocks(title="예비교사 과학 설명 훈련") as app:
        gr.Markdown(
            "## 🧠 예비교사 과학 설명 훈련\n"
            "동료 학습자(AI)에게 오늘 배운 단원을 설명해보세요.\n"
            "AI는 여러분의 설명을 들으며 질문합니다. "
            "**설명이 깊을수록 학습이 깊어져요.**"
        )

        session_state = gr.State(value=None)
        unit_code_state = gr.State(value="")
        completed_state = gr.State(value=False)

        # ---------------- Login pane ----------------
        with gr.Group(visible=True) as login_group:
            gr.Markdown("### 로그인")
            unit_display = gr.Markdown("*단원 정보를 확인하는 중...*")
            with gr.Row():
                sid_in = gr.Textbox(label="학생 ID", placeholder="예: s01", scale=2)
                pw_in = gr.Textbox(
                    label="비밀번호", placeholder="5자리", type="password", scale=2
                )
                login_btn = gr.Button("시작하기", variant="primary", scale=1)
            login_msg = gr.Markdown("")

        # ---------------- Chat pane ----------------
        with gr.Group(visible=False) as chat_group:
            status_out = gr.Markdown("")
            chatbot = gr.Chatbot(label="대화", height=460)
            with gr.Row():
                msg_in = gr.Textbox(
                    label="내 설명 입력",
                    placeholder="여기에 설명을 적고 Enter 또는 보내기를 눌러요.",
                    lines=2,
                    scale=5,
                )
                send_btn = gr.Button("보내기", variant="primary", scale=1)
            with gr.Row():
                complete_btn = gr.Button("대화 종료하고 리포트 받기", variant="stop")

        # ---------------- Completion pane ----------------
        with gr.Group(visible=False) as complete_group:
            gr.Markdown("### ✅ 세션이 종료되었습니다")
            complete_info = gr.Markdown("")
            gr.Markdown(
                "📄 **PDF 리포트 다운로드는 Phase B에서 제공됩니다.**\n"
                "지금은 대화 기록이 DB에 저장된 상태예요. 이후 분석/PDF 기능이 붙으면 "
                "이 화면에서 두 개의 PDF(요약본·상세본)를 내려받을 수 있어요."
            )

        # ---------------- handlers ----------------

        def on_load(request: gr.Request) -> tuple[Any, Any]:
            """Populate the unit banner based on ?unit= query param."""

            code = _parse_unit_code(request)
            if not code:
                return (
                    "⚠️ URL에 단원 정보가 없어요. 교수자가 알려준 링크(예: `?unit=photo-01`)로 "
                    "다시 접속해주세요.",
                    "",
                )
            # Validate the unit exists.
            try:
                mgr.load_unit(code)
            except AuthenticationError as exc:
                return f"⚠️ {exc}", ""

            # Show only the unit_code in UI, not the full unit_name, to avoid hinting content.
            return f"**단원 코드:** `{code}`\n\n학생 ID와 비밀번호를 입력하세요.", code

        def on_login(
            unit_code: str, sid: str, pw: str
        ) -> tuple[Any, Any, Any, Any, Any, Any, Any]:
            if not unit_code:
                return (
                    gr.update(visible=True),   # login_group
                    gr.update(visible=False),  # chat_group
                    gr.update(visible=False),  # complete_group
                    None,                      # session_state
                    "⚠️ 단원 코드가 없어요. 교수자에게 받은 링크로 접속해주세요.",  # login_msg
                    "",                        # status_out
                    [],                        # chatbot
                )
            try:
                result = mgr.login(unit_code, sid, pw)
            except AuthenticationError as exc:
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    None,
                    f"⚠️ {exc}",
                    "",
                    [],
                )
            except SessionLockedError as exc:
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    None,
                    f"🔒 {exc}",
                    "",
                    [],
                )

            status = (
                f"**{result.unit_config.persona_name}** 와 대화 중 · "
                f"단원: {result.unit_config.unit_name} · "
                f"ID: `{sid}`"
                + ("  (이어서 계속하기)" if not result.is_new else "")
            )
            return (
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                result.session_id,
                "",
                status,
                _render_history(result.turns),
            )

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
            except (ValueError, LookupError) as exc:
                return gr.update(), f"⚠️ 전송 실패: {exc}", user_text
            turns = mgr.get_turns(session_id)
            return _render_history(turns), gr.update(), ""

        def on_complete(session_id: str | None) -> tuple[Any, Any, Any, Any]:
            if not session_id:
                return (
                    gr.update(visible=False),
                    gr.update(visible=True),
                    gr.update(visible=False),
                    "세션이 없어요.",
                )
            try:
                mgr.complete_session(session_id)
            except LookupError as exc:
                return (
                    gr.update(visible=False),
                    gr.update(visible=True),
                    gr.update(visible=False),
                    f"⚠️ 종료 실패: {exc}",
                )
            info = (
                "오늘도 설명해주셔서 고마워요. 대화 기록이 안전하게 저장되었습니다.\n"
                f"세션 ID: `{session_id}`"
            )
            return (
                gr.update(visible=False),  # login_group
                gr.update(visible=False),  # chat_group
                gr.update(visible=True),   # complete_group
                info,
            )

        # ---------------- wiring ----------------

        app.load(on_load, inputs=None, outputs=[unit_display, unit_code_state])

        login_btn.click(
            on_login,
            inputs=[unit_code_state, sid_in, pw_in],
            outputs=[
                login_group,
                chat_group,
                complete_group,
                session_state,
                login_msg,
                status_out,
                chatbot,
            ],
        )

        send_btn.click(
            on_send,
            inputs=[session_state, msg_in],
            outputs=[chatbot, status_out, msg_in],
        )
        msg_in.submit(
            on_send,
            inputs=[session_state, msg_in],
            outputs=[chatbot, status_out, msg_in],
        )

        complete_btn.click(
            on_complete,
            inputs=[session_state],
            outputs=[login_group, chat_group, complete_group, complete_info],
        )

    return app
