"""Paragraph styles and color palette for the reports.

All styles centralise the Korean font name so swapping fonts affects
the whole document.
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, StyleSheet1

from src.services.pdf.fonts import register_korean_font

# Colour palette — keep consistent across summary + detail PDFs.
PRIMARY = colors.HexColor("#2F3E5F")
ACCENT = colors.HexColor("#4A6CF7")
MUTED = colors.HexColor("#6B7280")
DIVIDER = colors.HexColor("#D9DEE8")
OK_GREEN = colors.HexColor("#1B9E45")
WARN_AMBER = colors.HexColor("#C6A300")
ERR_RED = colors.HexColor("#D23A3A")
RUBRIC_HIT_BG = colors.HexColor("#E8F1FF")
MISCONCEPTION_BG = colors.HexColor("#FFECEC")


def build_styles() -> StyleSheet1:
    """Construct a reportlab StyleSheet1 wired to the registered Korean font."""

    regular, bold = register_korean_font()
    styles = StyleSheet1()

    styles.add(
        ParagraphStyle(
            "BodyKR",
            fontName=regular,
            fontSize=10,
            leading=14,
            textColor=PRIMARY,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodySmallKR",
            fontName=regular,
            fontSize=8.5,
            leading=12,
            textColor=PRIMARY,
        )
    )
    styles.add(
        ParagraphStyle(
            "MutedKR",
            fontName=regular,
            fontSize=9,
            leading=12,
            textColor=MUTED,
        )
    )
    styles.add(
        ParagraphStyle(
            "H1KR",
            fontName=bold,
            fontSize=20,
            leading=26,
            textColor=PRIMARY,
            spaceBefore=6,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            "H2KR",
            fontName=bold,
            fontSize=14,
            leading=18,
            textColor=PRIMARY,
            spaceBefore=14,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "H3KR",
            fontName=bold,
            fontSize=11,
            leading=15,
            textColor=ACCENT,
            spaceBefore=8,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            "Callout",
            fontName=regular,
            fontSize=9,
            leading=13,
            textColor=PRIMARY,
            backColor=RUBRIC_HIT_BG,
            borderPadding=6,
            borderColor=ACCENT,
            borderWidth=0.5,
            spaceBefore=4,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "Warning",
            fontName=regular,
            fontSize=9,
            leading=13,
            textColor=ERR_RED,
            backColor=MISCONCEPTION_BG,
            borderPadding=6,
            spaceBefore=4,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "CodeKR",
            fontName=regular,
            fontSize=8.5,
            leading=11,
            textColor=PRIMARY,
            backColor=colors.HexColor("#F4F5FA"),
            borderPadding=6,
            leftIndent=6,
        )
    )
    return styles
