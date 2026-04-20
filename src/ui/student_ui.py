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
from src.ui.concept_map_editor import (
    build_visual_concept_map_editor,
    parse_visual_concept_map,
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


def _progress_html(active_pane: str) -> str:
    """Produce the progress-dots HTML with the current pane highlighted."""

    steps = [
        ("login", "1. 로그인"),
        ("pre_map", "2. 초기 개념도"),
        ("dialogue", "3. 대화"),
        ("post_map", "4. 사후 개념도"),
        ("reflection", "5. 성찰"),
        ("completed", "6. 완료"),
    ]
    active_idx = next(
        (i for i, (p, _) in enumerate(steps) if p == active_pane), 0
    )
    parts: list[str] = []
    for i, (_, label) in enumerate(steps):
        if i < active_idx:
            parts.append(f"✅ {label}")
        elif i == active_idx:
            parts.append(f"🟢 <b>{label}</b>")
        else:
            parts.append(f"⚪ {label}")
    joined = "  →  ".join(parts)
    return f"<div class='progress-dots'>{joined}</div>"


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

    _student_theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="indigo",
        neutral_hue="slate",
        radius_size=gr.themes.sizes.radius_md,
        spacing_size=gr.themes.sizes.spacing_md,
        font=[gr.themes.GoogleFont("Nanum Gothic"), "system-ui", "sans-serif"],
    )

    # Heavy custom CSS — makes the app feel less "gradio demo" and more like
    # a real tool. Typography + soft cards + consistent spacing + visual
    # editor styling.
    _css = """
    :root {
      --cm-primary: #4f46e5;
      --cm-primary-dark: #3730a3;
      --cm-surface: #ffffff;
      --cm-muted: #64748b;
      --cm-border: #e2e8f0;
      --cm-tint: #eef2ff;
    }
    .gradio-container {
      max-width: 1080px !important;
      margin: 0 auto !important;
      padding: 14px 18px 32px !important;
      font-family: "Nanum Gothic", "Pretendard", "Noto Sans KR",
                   system-ui, -apple-system, sans-serif !important;
    }
    .gradio-container h1,
    .gradio-container h2,
    .gradio-container h3 { letter-spacing: -0.01em; }
    .progress-dots {
      display: flex; gap: 10px; align-items: center;
      flex-wrap: wrap;
      font-size: 0.9rem;
      padding: 12px 16px; margin: 10px 0 20px 0;
      background: linear-gradient(90deg, #EEF2FF 0%, #F8FAFC 100%);
      border-radius: 14px; border: 1px solid var(--cm-border);
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .progress-dots b { color: var(--cm-primary-dark); }
    footer { display: none !important; }
    .gr-block.gr-box, .block { border-radius: 14px !important; }
    .gr-button {
      border-radius: 10px !important;
      font-weight: 600 !important;
      letter-spacing: -0.005em;
    }
    .gr-button.primary {
      box-shadow: 0 1px 3px rgba(79, 70, 229, 0.3);
    }
    .gr-textbox textarea,
    .gr-textbox input {
      font-family: "Nanum Gothic", "Pretendard", "Noto Sans KR",
                   system-ui, sans-serif !important;
      font-size: 0.95rem !important;
      line-height: 1.55 !important;
    }

    /* Visual concept-map editor styling */
    .cm-wrapper {
      border: 1px solid var(--cm-border);
      border-radius: 14px;
      background: var(--cm-surface);
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    }
    .cm-toolbar {
      display: flex; flex-wrap: wrap; gap: 8px;
      padding: 10px 14px;
      background: linear-gradient(180deg, #F8FAFC, #F1F5F9);
      border-bottom: 1px solid var(--cm-border);
      align-items: center;
    }
    .cm-btn {
      background: var(--cm-primary);
      color: white;
      border: none;
      border-radius: 10px;
      padding: 8px 14px;
      font-weight: 600;
      font-size: 0.88rem;
      cursor: pointer;
      transition: transform 0.05s, box-shadow 0.15s, background 0.15s;
      box-shadow: 0 1px 2px rgba(79, 70, 229, 0.25);
    }
    .cm-btn:hover { background: var(--cm-primary-dark); }
    .cm-btn:active { transform: translateY(1px); }
    .cm-btn-muted {
      background: #f1f5f9; color: #475569; box-shadow: none;
    }
    .cm-btn-muted:hover { background: #e2e8f0; }
    .cm-hint {
      font-size: 0.82rem; color: var(--cm-muted);
      margin-left: auto;
    }
    .cm-canvas-wrap {
      background:
        radial-gradient(circle, #e2e8f0 1px, transparent 1.5px) 0 0 / 22px 22px,
        #fafafa;
      position: relative;
    }
    .cm-svg { display: block; cursor: crosshair; }
    .cm-node { cursor: move; }
    .cm-node:hover rect { stroke-width: 2; }
    .cm-edge:hover { stroke-width: 3; }
    .cm-stats {
      padding: 8px 14px;
      font-size: 0.84rem;
      color: var(--cm-muted);
      border-top: 1px solid var(--cm-border);
      background: #f8fafc;
    }
    """

    with gr.Blocks(title="예비교사 과학 설명 훈련", theme=_student_theme, css=_css) as app:
        gr.Markdown(
            """
            ## 🧠 예비교사 과학 설명 훈련
            > 동료 학습자(AI)에게 오늘 배운 단원을 설명하며 본인 이해를 깊게 하는 활동입니다.
            > 모든 단계를 마치면 교수자에게 낼 리포트(PDF)가 생성돼요.
            """
        )
        step_progress = gr.Markdown(
            "<div class='progress-dots'>"
            "🟢 <b>1. 로그인</b>  →  ⚪ 2. 초기 개념도  →  ⚪ 3. 대화  "
            "→  ⚪ 4. 사후 개념도  →  ⚪ 5. 성찰  →  ⚪ 6. 완료"
            "</div>"
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
                sid_in = gr.Textbox(
                    label="학번",
                    placeholder="예: 2021001",
                    scale=2,
                )
                name_in = gr.Textbox(
                    label="이름",
                    placeholder="예: 홍길동",
                    scale=2,
                )
                pw_in = gr.Textbox(
                    label="비밀번호(선택, 예전 방식만)",
                    placeholder="보통 비워두세요",
                    type="password",
                    scale=1,
                )
                login_btn = gr.Button("시작하기", variant="primary", scale=1)
            login_msg = gr.Markdown("")

        # =========================================================================
        # Pane 2: PRE_MAP
        # =========================================================================
        with gr.Group(visible=False) as pre_map_pane:
            gr.Markdown(
                "### 2단계 · 🗺️ 초기 개념도 그리기\n"
                "> 마우스로 **개념**을 놓고 **선**을 그어 연결하세요. 구조만 잡으면 됩니다."
            )
            pre_map_editor = build_visual_concept_map_editor(prefix="pre_map")
            pre_map_warnings = gr.Markdown("")
            pre_map_submit = gr.Button(
                "✅ 개념도 제출 → AI 대화 시작",
                variant="primary",
                size="lg",
            )

        # =========================================================================
        # Pane 3: DIALOGUE
        # =========================================================================
        with gr.Group(visible=False) as dialogue_pane:
            gr.Markdown("### 3단계. 동료 학습자와의 대화")
            dialogue_status = gr.Markdown("")
            # type='tuples' keeps the legacy [[student, ai], ...] format that
            # _render_history builds. Gradio 5 defaults to 'messages' but both
            # are supported.
            dialogue_chatbot = gr.Chatbot(
                label="대화",
                height=460,
                type="tuples",
                show_copy_button=True,
                show_label=False,
                avatar_images=(None, None),
                bubble_full_width=False,
            )
            with gr.Row():
                msg_in = gr.Textbox(
                    label="내 설명",
                    placeholder="AI에게 설명하고 싶은 내용을 적고 Enter 또는 보내기",
                    lines=2,
                    scale=6,
                    show_label=False,
                )
                send_btn = gr.Button("✉️ 보내기", variant="primary", scale=1, size="lg")

            # -------- Vygotsky scaffolding hints --------
            with gr.Accordion(
                "💡 막힐 때 눌러보세요 · 비계 힌트 (남은 횟수 표시)", open=False
            ):
                hints_remaining_md = gr.Markdown("남은 힌트: **3회**")
                gr.Markdown(
                    "각 힌트는 **서로 다른 방식의 작은 단서**를 줍니다. "
                    "답을 주지는 않고, 여러분이 다음 스텝을 찾도록 돕는 한 문장이에요."
                )
                with gr.Row():
                    hint_socratic_btn = gr.Button(
                        "🗣 소크라테스 되묻기", size="sm"
                    )
                    hint_bridging_btn = gr.Button(
                        "🌉 개념 잇기 (다리)", size="sm"
                    )
                    hint_counter_btn = gr.Button(
                        "⚖️ 반례 던지기", size="sm"
                    )
                with gr.Row():
                    hint_evidence_btn = gr.Button(
                        "🔬 증거·근거", size="sm"
                    )
                    hint_repr_btn = gr.Button(
                        "🎨 표상 바꾸기", size="sm"
                    )
                    hint_meta_btn = gr.Button(
                        "🧠 메타인지", size="sm"
                    )
                hint_msg = gr.Markdown("")

            with gr.Row():
                end_dialogue_btn = gr.Button(
                    "✅ 대화 종료 → 사후 개념도로",
                    variant="stop",
                )

        # =========================================================================
        # Pane 4: POST_MAP
        # =========================================================================
        with gr.Group(visible=False) as post_map_pane:
            gr.Markdown(
                "### 4단계 · 🗺️ 대화 후 개념도 다시 그리기\n"
                "> 대화를 통해 바뀐 이해를 반영해 다시 그려주세요. 초기 개념도는 "
                "**비교 편향을 줄이기 위해** 보여드리지 않습니다."
            )
            post_map_editor = build_visual_concept_map_editor(prefix="post_map")
            post_map_warnings = gr.Markdown("")
            post_map_submit = gr.Button(
                "✅ 사후 개념도 제출 → 성찰 질문으로",
                variant="primary",
                size="lg",
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

            ai_status = ""
            if not mgr.ai_is_ready():
                ai_status = (
                    "\n\n⚠️ **지금 AI 가 응답할 준비가 되지 않았어요.**\n"
                    "교수자가 관리자 페이지에서 API 키 설정을 마칠 때까지 잠시 기다려주세요. "
                    "그래도 계속 로그인해서 개념도는 작성할 수 있어요 — AI 가 켜지면 대화가 이어집니다."
                )
            return (
                f"**단원 코드:** `{code}`\n\n학번과 이름을 입력하세요." + ai_status,
                code,
            )

        def on_login(
            unit_code: str, sid: str, name: str, pw: str
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
                result = mgr.login(unit_code, sid, pw, student_name=name)
            except AuthenticationError as exc:
                return (*_show("login"), None, f"⚠️ {exc}", "", [])
            except SessionLockedError as exc:
                return (*_show("login"), None, f"🔒 {exc}", "", [])

            pane = _step_to_pane(result.current_step)
            greeting_id = f"{sid} ({name})" if name else sid
            status = (
                f"**{result.unit_config.persona_name}** 와 대화 중 · "
                f"단원: {result.unit_config.unit_name} · ID: `{greeting_id}`"
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
            state_json: str,
        ) -> tuple[Any, ...]:
            if not session_id:
                return (*_show("login"), "⚠️ 로그인 먼저 하세요.", "", [])
            try:
                cmap = parse_visual_concept_map(state_json)
            except ValueError as exc:
                return (*_show("pre_map"), f"⚠️ {exc}", "", [])

            try:
                result = mgr.submit_pre_concept_map(session_id, cmap)
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

        def _hint_counter_text(session_id: str | None) -> str:
            if not session_id:
                return "남은 힌트: **?**"
            try:
                from src.db.repository import SessionRepository

                remaining = SessionRepository().get_hints_remaining(session_id)
                return f"남은 힌트: **{remaining}회**"
            except Exception:  # noqa: BLE001
                return "남은 힌트: **?**"

        def _on_hint(session_id: str | None, hint_type_value: str) -> tuple[Any, Any, Any]:
            """Common handler for the 6 hint buttons."""

            if not session_id:
                return gr.update(), "⚠️ 먼저 로그인하세요.", gr.update()
            try:
                from src.models.enums import HintType

                ht = HintType(hint_type_value)
            except ValueError:
                return gr.update(), "⚠️ 알 수 없는 힌트 유형.", gr.update()
            try:
                mgr.request_hint(session_id, ht)
            except ValueError as exc:
                return gr.update(), f"⚠️ {exc}", _hint_counter_text(session_id)
            except (SessionLockedError, LookupError) as exc:
                return gr.update(), f"⚠️ {exc}", _hint_counter_text(session_id)
            turns = mgr.get_turns(session_id)
            return _render_history(turns), "", _hint_counter_text(session_id)

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
            state_json: str,
        ) -> tuple[Any, ...]:
            if not session_id:
                return (*_show("login"), "")
            try:
                cmap = parse_visual_concept_map(state_json)
            except ValueError as exc:
                return (*_show("post_map"), f"⚠️ {exc}")
            try:
                mgr.submit_post_concept_map(session_id, cmap)
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
            inputs=[unit_code_state, sid_in, name_in, pw_in],
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

        pre_map_submit.click(
            on_submit_pre_map,
            inputs=[session_state, pre_map_editor["state_in"]],
            outputs=[
                login_pane,
                pre_map_pane,
                dialogue_pane,
                post_map_pane,
                reflection_pane,
                completed_pane,
                pre_map_warnings,
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

        # Hint button wiring — each one calls _on_hint with its type
        for _btn, _type_val in [
            (hint_socratic_btn, "socratic"),
            (hint_bridging_btn, "bridging"),
            (hint_counter_btn, "counterexample"),
            (hint_evidence_btn, "evidence"),
            (hint_repr_btn, "representation"),
            (hint_meta_btn, "metacognitive"),
        ]:
            # Using closure capture via default arg
            _btn.click(
                (lambda sid, tv=_type_val: _on_hint(sid, tv)),
                inputs=[session_state],
                outputs=[dialogue_chatbot, hint_msg, hints_remaining_md],
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

        post_map_submit.click(
            on_submit_post_map,
            inputs=[session_state, post_map_editor["state_in"]],
            outputs=[
                login_pane,
                pre_map_pane,
                dialogue_pane,
                post_map_pane,
                reflection_pane,
                completed_pane,
                post_map_warnings,
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
