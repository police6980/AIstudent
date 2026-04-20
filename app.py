"""Hugging Face Spaces entrypoint.

HF Spaces looks for `demo` (or `app`) in app.py and auto-launches it.
We reuse the same student + instructor composition as src.main, but
without `share=True` (Spaces provides its own public URL).

Environment variables (set these as HF Space Secrets):
    ANTHROPIC_API_KEY      — required for all AI calls
    CLAUDE_MODEL           — optional, default claude-sonnet-4-6
    CLAUDE_ANALYSIS_MODEL  — optional, default claude-opus-4-7
    INSTRUCTOR_PASSWORD    — optional, enables ?admin=true page
"""

from __future__ import annotations

import logging

import gradio as gr

from src.config.settings import get_settings
from src.db.database import init_db
from src.ui.instructor_ui import build_instructor_app
from src.ui.student_ui import build_student_app

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

settings = get_settings()
if not settings.anthropic_api_key:
    logging.warning(
        "ANTHROPIC_API_KEY is not set. The UI will load, but AI replies will fail "
        "until the secret is configured in the Space settings."
    )

init_db()

_student_app = build_student_app()
_instructor_app = build_instructor_app()

with gr.Blocks(title="예비교사 과학 설명 훈련") as demo:
    with gr.Group(visible=True) as _student_group:
        _student_app.render()
    with gr.Group(visible=False) as _instructor_group:
        _instructor_app.render()

    def _on_load(request: gr.Request) -> tuple:
        try:
            params = request.query_params
            admin_flag = (params.get("admin") or "").strip().lower()
        except Exception:  # pragma: no cover - defensive
            admin_flag = ""
        show_admin = admin_flag in {"true", "1", "yes"}
        return (
            gr.update(visible=not show_admin),
            gr.update(visible=show_admin),
        )

    demo.load(_on_load, inputs=None, outputs=[_student_group, _instructor_group])


if __name__ == "__main__":
    # show_api=False skips the /api schema endpoint, which gradio_client
    # tries to build from our Blocks and choked on when boolean
    # additionalProperties appeared in Pydantic-derived schemas. We don't
    # expose a JSON API to students, so disabling it is safe.
    demo.launch(show_api=False)
