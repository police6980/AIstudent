"""Register a Korean-capable font with reportlab.

Strategy (tried in order):
    1. Scan common OS paths for NanumGothic / Noto Sans CJK KR / Malgun Gothic.
       If found, register with `TTFont` under the name 'KoreanSans'.
    2. Fall back to reportlab's built-in CID font 'HeiseiKakuGo-W5'
       (technically Japanese, but has sufficient Han + Hangul coverage in most
       PDF viewers). Registered under 'KoreanSans' so downstream code always
       uses the same style name.
    3. As a last resort, use the default Helvetica — Korean will render as
       tofu but the PDF still generates and the English/numeric structure is
       readable. We log a clear warning so the instructor knows to install a
       Korean font.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

KOREAN_FONT_NAME = "KoreanSans"
KOREAN_FONT_BOLD = "KoreanSans-Bold"

_SEARCH_PATHS: list[Path] = [
    # Linux
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf"),
    # macOS
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    Path("/Library/Fonts/AppleGothic.ttf"),
    # Windows
    Path("C:/Windows/Fonts/malgun.ttf"),
    Path("C:/Windows/Fonts/malgunbd.ttf"),
    # Common user-install locations
    Path.home() / ".fonts" / "NanumGothic.ttf",
    Path.home() / "Library" / "Fonts" / "NanumGothic.ttf",
]


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        try:
            if p.exists():
                return p
        except OSError:
            continue
    return None


def _pick_regular() -> Path | None:
    return _first_existing(
        [
            Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
            Path("/Library/Fonts/AppleGothic.ttf"),
            Path("C:/Windows/Fonts/malgun.ttf"),
            Path.home() / ".fonts" / "NanumGothic.ttf",
        ]
    )


def _pick_bold() -> Path | None:
    return _first_existing(
        [
            Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
            Path("C:/Windows/Fonts/malgunbd.ttf"),
        ]
    )


@lru_cache(maxsize=1)
def register_korean_font() -> tuple[str, str]:
    """Register the best available Korean font and return (regular, bold) names.

    Safe to call repeatedly — the lru_cache ensures single registration per
    process. Downstream PDF code uses the returned names only.
    """

    regular = _pick_regular()
    bold = _pick_bold()

    try:
        if regular is not None:
            pdfmetrics.registerFont(TTFont(KOREAN_FONT_NAME, str(regular)))
            logger.info("Registered Korean font: %s", regular)
            if bold is not None:
                pdfmetrics.registerFont(TTFont(KOREAN_FONT_BOLD, str(bold)))
                logger.info("Registered Korean bold font: %s", bold)
                return KOREAN_FONT_NAME, KOREAN_FONT_BOLD
            # No bold variant — reuse regular for bold styles.
            return KOREAN_FONT_NAME, KOREAN_FONT_NAME
    except Exception as exc:  # pragma: no cover - depends on host fonts
        logger.warning("TTF registration failed (%s). Falling back to CID.", exc)

    # Fallback 1: reportlab's built-in CID font covers Hangul + Han.
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        logger.warning(
            "No Korean TrueType found. Using CID fallback 'HeiseiKakuGo-W5'. "
            "For best rendering, install NanumGothic or Noto Sans CJK KR."
        )
        return "HeiseiKakuGo-W5", "HeiseiKakuGo-W5"
    except Exception as exc:  # pragma: no cover - rare
        logger.warning("CID font registration failed (%s). PDF may show tofu for Korean.", exc)

    # Fallback 2: default Helvetica. Korean will render as tofu.
    logger.error(
        "No Korean font available. PDFs will render Hangul as missing glyphs. "
        "Install NanumGothic (apt install fonts-nanum on Linux) or Noto Sans CJK KR."
    )
    return "Helvetica", "Helvetica-Bold"
