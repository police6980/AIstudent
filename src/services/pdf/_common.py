"""Shared helpers used by both summary_pdf and detail_pdf builders."""

from __future__ import annotations

import html as _html
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from src.services.pdf.styles import ACCENT, DIVIDER, MUTED, PRIMARY


def esc(text: Any) -> str:
    """HTML-escape for reportlab Paragraph. Handles non-strings gracefully."""

    if text is None:
        return ""
    return _html.escape(str(text))


def image_from_bytes(data: bytes, width_cm: float) -> Image:
    """Build a reportlab Image from PNG bytes at a specified width (cm)."""

    buf = BytesIO(data)
    img = Image(buf)
    aspect = img.drawHeight / img.drawWidth if img.drawWidth else 1.0
    img.drawWidth = width_cm * cm
    img.drawHeight = width_cm * cm * aspect
    return img


def kv_table(rows: list[tuple[str, str]], styles, col_widths=None) -> Table:
    """Two-column key/value table with a subtle divider."""

    data = [
        [Paragraph(f"<b>{esc(k)}</b>", styles["BodyKR"]), Paragraph(esc(v), styles["BodyKR"])]
        for k, v in rows
    ]
    t = Table(data, colWidths=col_widths or [4.0 * cm, 11.0 * cm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, DIVIDER),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def rubric_table(
    rubric_items_achieved: dict[str, bool],
    rubric_labels: dict[str, str],
    styles,
) -> Table:
    """Rubric achievement table: ✓/✗ + label + id."""

    header = [
        Paragraph("<b>상태</b>", styles["BodyKR"]),
        Paragraph("<b>루브릭 항목</b>", styles["BodyKR"]),
        Paragraph("<b>ID</b>", styles["BodyKR"]),
    ]
    rows = [header]
    for item_id, achieved in rubric_items_achieved.items():
        # NanumGothic lacks ✅/❌ emoji glyphs, so we use coloured O/X that
        # render reliably on any installed Korean font.
        mark_html = (
            "<font color='#1B9E45'><b>O</b></font>"
            if achieved
            else "<font color='#D23A3A'><b>X</b></font>"
        )
        rows.append(
            [
                Paragraph(mark_html, styles["BodyKR"]),
                Paragraph(esc(rubric_labels.get(item_id, "")), styles["BodyKR"]),
                Paragraph(esc(item_id), styles["BodySmallKR"]),
            ]
        )
    t = Table(rows, colWidths=[1.4 * cm, 9.5 * cm, 4.0 * cm], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F6FD")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.2, DIVIDER),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def bullet_list(items: list[str], styles, *, empty_text: str = "(없음)"):
    """Return a list of Paragraphs formatted as bullet items."""

    if not items:
        return [Paragraph(empty_text, styles["MutedKR"])]
    return [Paragraph(f"• {esc(it)}", styles["BodyKR"]) for it in items]


def labeled_callout(title: str, body: str, styles):
    """Boxed callout paragraph for strengths/growth points etc."""

    return Paragraph(f"<b>{esc(title)}</b> — {esc(body)}", styles["Callout"])


def section_heading(text: str, styles):
    return Paragraph(esc(text), styles["H2KR"])


def sub_heading(text: str, styles):
    return Paragraph(esc(text), styles["H3KR"])


def footer_note(text: str, styles):
    return Paragraph(f"<i>{esc(text)}</i>", styles["MutedKR"])


def vspace(h: float = 0.3):
    return Spacer(1, h * cm)
