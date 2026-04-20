"""Hugging Face Spaces entrypoint."""

from __future__ import annotations


def _patch_gradio_client_bool_schema_bug() -> None:
    """gradio_client keeps raising TypeError on Pydantic bool schemas,
    including under gradio 5. Patch both entry points to return 'Any'
    when a bool lands where a dict is expected."""

    import gradio_client.utils as _gcu

    _orig_get_type = _gcu.get_type
    _orig_jspt = _gcu._json_schema_to_python_type

    def _safe_get_type(schema):
        if isinstance(schema, bool):
            return "Any"
        return _orig_get_type(schema)

    def _safe_jspt(schema, defs=None):
        if isinstance(schema, bool):
            return "Any"
        return _orig_jspt(schema, defs)

    _gcu.get_type = _safe_get_type
    _gcu._json_schema_to_python_type = _safe_jspt


_patch_gradio_client_bool_schema_bug()


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
        except Exception:
            admin_flag = ""
        show_admin = admin_flag in {"true", "1", "yes"}
        return (
            gr.update(visible=not show_admin),
            gr.update(visible=show_admin),
        )

    demo.load(_on_load, inputs=None, outputs=[_student_group, _instructor_group])


demo.launch()
