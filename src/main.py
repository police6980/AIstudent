"""Gradio app entrypoint for M1 text chat.

Run with: `python -m src.main`
"""

from __future__ import annotations

import logging

from src.config.settings import get_settings
from src.db.database import init_db
from src.ui.student_ui import build_student_app


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    settings = get_settings()
    _configure_logging(settings.log_level)

    if not settings.anthropic_api_key:
        logging.warning(
            "ANTHROPIC_API_KEY is not set. The UI will start, but AI replies will fail until "
            "the key is configured in .env."
        )

    init_db()
    app = build_student_app()
    app.launch()


if __name__ == "__main__":
    main()
