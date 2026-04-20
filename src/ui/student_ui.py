"""Minimal Gradio student UI (M1: text-only chat).

Voice input/output (STT + TTS) and hint buttons are added in M2/M3.
"""

from __future__ import annotations

from typing import Any

import gradio as gr

from src.models.enums import Speaker
from src.services.session_manager import SessionManager


def _render_history(turns) -> list[tuple[str, str]]:
    """Format Turn list into Gradio Chatbot pairs: (student_msg, ai_msg)."""

    pairs: list[list[str | None]] = []
    pending_student: str | None = None
    for t in turns:
        if t.speaker == Speaker.STUDENT:
            pending_student = t.content
            pairs.append([pending_student, None])
        else:  # AI
            if pairs and pairs[-1][1] is None:
                pairs[-1][1] = t.content
            else:
                pairs.append([None, t.content])
            pending_student = None
    return [tuple(p) for p in pairs]  # type: ignore[misc]


def build_student_app(manager: SessionManager | None = None) -> gr.Blocks:
    """Return a Gradio Blocks app for student text chat."""

    mgr = manager or SessionManager()

    with gr.Blocks(title="Vygotsky Science Tutor — M1") as app:
        gr.Markdown(
            "## 🤖 과학 학습 친구와 대화해요 (M1 · 텍스트 모드)\n"
            "- 실명 대신 **닉네임** 사용을 권장해요.\n"
            "- 세션 코드는 선생님이 알려주신 값을 입력해요."
        )

        session_state = gr.State(value=None)

        with gr.Row():
            code_in = gr.Textbox(label="세션 코드", placeholder="예: photo-g6-0420", scale=2)
            name_in = gr.Textbox(label="내 닉네임", placeholder="예: 호랑이", scale=2)
            start_btn = gr.Button("세션 시작", variant="primary", scale=1)

        status_out = gr.Markdown("아직 세션이 시작되지 않았어요.")
        chatbot = gr.Chatbot(label="대화", height=420)

        with gr.Row():
            msg_in = gr.Textbox(
                label="내가 설명하기",
                placeholder="여기에 입력하고 Enter를 눌러요.",
                lines=2,
                scale=5,
            )
            send_btn = gr.Button("보내기", variant="primary", scale=1)

        with gr.Row():
            end_btn = gr.Button("세션 종료", variant="stop")

        # --- handlers ---

        def on_start(code: str, nickname: str) -> tuple[Any, Any, Any]:
            code = (code or "").strip()
            nickname = (nickname or "").strip() or "익명"
            if not code:
                return (
                    None,
                    "⚠️ 세션 코드를 입력해 주세요.",
                    [],
                )
            try:
                result = mgr.start_session(code, nickname)
            except (ValueError, LookupError) as exc:
                return None, f"⚠️ 시작 실패: {exc}", []

            turns = mgr.get_turns(result.session_id)
            history_ui = _render_history(turns)
            status = (
                f"✅ **{result.unit_config.persona_name}** 와 대화 중 · "
                f"단원: {result.unit_config.unit_name} · "
                f"학교급: {result.unit_config.grade_level.value}"
            )
            return result.session_id, status, history_ui

        def on_send(session_id: str | None, user_text: str) -> tuple[Any, Any, Any]:
            user_text = (user_text or "").strip()
            if not session_id:
                return gr.update(), "⚠️ 먼저 세션을 시작하세요.", ""
            if not user_text:
                return gr.update(), gr.update(), ""
            try:
                mgr.submit_student_turn(session_id, user_text)
            except (ValueError, LookupError) as exc:
                return gr.update(), f"⚠️ 전송 실패: {exc}", user_text
            turns = mgr.get_turns(session_id)
            return _render_history(turns), gr.update(), ""

        def on_end(session_id: str | None) -> str:
            if not session_id:
                return "세션이 없습니다."
            try:
                mgr.end_session(session_id)
            except LookupError as exc:
                return f"⚠️ 종료 실패: {exc}"
            return "✅ 세션을 종료했어요. 오늘도 잘 설명해줘서 고마워요."

        start_btn.click(
            on_start,
            inputs=[code_in, name_in],
            outputs=[session_state, status_out, chatbot],
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
        end_btn.click(on_end, inputs=[session_state], outputs=[status_out])

    return app
