"""Gradio app entrypoint.

Routing:
  http://<host>/              → student login + chat UI
  http://<host>/?unit=xxx     → student UI targeted at unit xxx
  http://<host>/?admin=true   → instructor management UI

Run with: `python -m src.main`
"""

from __future__ import annotations

import logging

import gradio as gr

from src.config.settings import get_settings
from src.db.database import init_db
from src.ui.instructor_ui import build_instructor_app
from src.ui.student_ui import build_student_app


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_root_app() -> gr.Blocks:
    """Compose the student and instructor apps into one Blocks.

    Gradio's `app.load` can inspect the query string and switch between
    the two surfaces: student view vs instructor view.
    """

    student_app = build_student_app()
    instructor_app = build_instructor_app()

    with gr.Blocks(title="예비교사 과학 설명 훈련") as root:
        student_visible = gr.State(value=True)

        with gr.Group(visible=True) as student_group:
            student_app.render()
        with gr.Group(visible=False) as instructor_group:
            instructor_app.render()

        def on_load(request: gr.Request) -> tuple:
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

        root.load(on_load, inputs=None, outputs=[student_group, instructor_group])

    return root


def main() -> None:
    settings = get_settings()
    _configure_logging(settings.log_level)

    if not settings.anthropic_api_key:
        logging.warning(
            "ANTHROPIC_API_KEY is not set. The UI will start, but AI replies will fail until "
            "the key is configured in .env."
        )
    if not settings.instructor_password:
        logging.info(
            "INSTRUCTOR_PASSWORD is not set. The ?admin=true management page is disabled."
        )

    init_db()
    app = build_root_app()
    app.launch()


if __name__ == "__main__":
    main()
