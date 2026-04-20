"""Gradio UI components."""

from src.ui.instructor_ui import build_instructor_app
from src.ui.student_ui import build_student_app

__all__ = ["build_student_app", "build_instructor_app"]
