"""Matplotlib chart generators for the PDF reports.

Each function returns raw PNG bytes so the PDF builder can embed them via
reportlab.platypus.Image directly (no intermediate files on disk).
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager

logger = logging.getLogger(__name__)

_PREFERRED_KR_FONTS = (
    "NanumGothic",
    "Noto Sans CJK KR",
    "Noto Sans KR",
    "Malgun Gothic",
    "AppleGothic",
    "Apple SD Gothic Neo",
)


def _refresh_font_cache_if_stale() -> None:
    """If no CJK font is visible, scan common system paths and add them."""

    names = {f.name for f in font_manager.fontManager.ttflist}
    if any(n in names for n in _PREFERRED_KR_FONTS):
        return
    candidates = [
        "/usr/share/fonts/truetype/nanum",
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/noto",
    ]
    added = 0
    for d in candidates:
        try:
            for fp in font_manager.findSystemFonts(fontpaths=d):
                try:
                    font_manager.fontManager.addfont(fp)
                    added += 1
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            continue
    if added:
        logger.info("Registered %d CJK font files with matplotlib.", added)


def _apply_korean_font() -> None:
    _refresh_font_cache_if_stale()
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _PREFERRED_KR_FONTS:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


def _fig_to_png(fig) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def render_novak_score_bars(pre_score: float, post_score: float) -> bytes:
    """Side-by-side bar chart of pre vs post Novak scores."""

    _apply_korean_font()
    fig, ax = plt.subplots(figsize=(4.5, 3))
    labels = ["초기", "사후"]
    values = [float(pre_score), float(post_score)]
    colors = ["#A0A4C0", "#4A6CF7"]
    bars = ax.bar(labels, values, color=colors, width=0.5, edgecolor="#2F3E5F")
    ax.set_title("Novak 점수 변화", fontsize=12)
    ax.set_ylabel("점수")
    ymax = max(values + [10]) * 1.2
    ax.set_ylim(0, ymax)
    for b, v in zip(bars, values):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v + ymax * 0.02,
            f"{v:.1f}",
            ha="center",
            fontsize=10,
            color="#2F3E5F",
        )
    delta = values[1] - values[0]
    ax.text(
        0.5,
        0.98,
        f"Δ = {delta:+.1f}",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=10,
        color="#1B9E45" if delta >= 0 else "#D23A3A",
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_png(fig)


def render_rubric_donut(achieved_map: dict[str, bool]) -> bytes:
    """Donut chart showing achieved vs not-achieved rubric item counts."""

    _apply_korean_font()
    achieved = sum(1 for v in achieved_map.values() if v)
    total = len(achieved_map)
    missed = total - achieved

    fig, ax = plt.subplots(figsize=(3.5, 3.5))
    if total == 0:
        ax.text(0.5, 0.5, "루브릭 없음", ha="center", va="center")
        ax.axis("off")
        return _fig_to_png(fig)

    wedges, _ = ax.pie(
        [achieved, max(missed, 0)],
        colors=["#4A6CF7", "#E5E7F0"],
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.35, "edgecolor": "white", "linewidth": 2},
    )
    ax.text(
        0,
        0.05,
        f"{achieved}/{total}",
        ha="center",
        va="center",
        fontsize=22,
        color="#2F3E5F",
        fontweight="bold",
    )
    ax.text(0, -0.2, "루브릭 달성", ha="center", va="center", fontsize=10, color="#6B7280")
    ax.set_title("루브릭 달성도", fontsize=12)
    return _fig_to_png(fig)


def render_misconception_states(trajectories: list[dict[str, Any]]) -> bytes:
    """Stacked horizontal bar showing count of final states across misconceptions."""

    _apply_korean_font()
    labels = ["해소", "부분 해소", "미해소", "새로 발생"]
    keys = ["resolved", "partially_resolved", "unresolved", "newly_emerged"]
    colors = ["#1B9E45", "#C6A300", "#D23A3A", "#6B7280"]

    counts = [0, 0, 0, 0]
    for t in trajectories or []:
        state = (t.get("final_state") or "").strip() if isinstance(t, dict) else ""
        if state in keys:
            counts[keys.index(state)] += 1

    fig, ax = plt.subplots(figsize=(5, 2.2))
    if sum(counts) == 0:
        ax.text(0.5, 0.5, "오개念 궤적 데이터 없음", ha="center", va="center")
        ax.axis("off")
        return _fig_to_png(fig)

    left = 0.0
    for count, label, color in zip(counts, labels, colors):
        if count <= 0:
            continue
        ax.barh(
            [0], [count], left=left, color=color, edgecolor="white", height=0.4, label=label
        )
        ax.text(
            left + count / 2,
            0,
            f"{label}\n{count}",
            ha="center",
            va="center",
            fontsize=8,
            color="white",
        )
        left += count

    ax.set_title("오개념 최종 상태", fontsize=12)
    ax.set_xlim(0, sum(counts))
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")
    return _fig_to_png(fig)


def render_explanation_trajectory(segments: list[dict[str, Any]]) -> bytes:
    """Line chart of explanation quality (clarity/depth/structure) across segments."""

    _apply_korean_font()
    fig, ax = plt.subplots(figsize=(5.5, 3))
    if not segments:
        ax.text(0.5, 0.5, "설명 품질 데이터 없음", ha="center", va="center")
        ax.axis("off")
        return _fig_to_png(fig)

    xs = list(range(1, len(segments) + 1))
    clarity = [float(s.get("clarity", 0) or 0) for s in segments]
    depth = [float(s.get("depth", 0) or 0) for s in segments]
    structure = [float(s.get("structure", 0) or 0) for s in segments]

    ax.plot(xs, clarity, marker="o", color="#4A6CF7", label="명료성")
    ax.plot(xs, depth, marker="s", color="#1B9E45", label="깊이")
    ax.plot(xs, structure, marker="^", color="#C6A300", label="구조")
    ax.set_xticks(xs)
    ax.set_xticklabels([f"구간 {i}" for i in xs])
    ax.set_ylim(0, 5.5)
    ax.set_ylabel("점수 (0-5)")
    ax.set_title("설명 품질 궤적", fontsize=12)
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.legend(loc="lower right", fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_png(fig)
