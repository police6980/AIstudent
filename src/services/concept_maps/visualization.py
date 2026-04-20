"""Render a concept map to a PNG image using networkx + matplotlib.

Layout strategy:
    - Propositions are laid out hierarchically using the computed levels
      (roots at top, deeper concepts lower).
    - Cross-links are drawn as dashed red edges over the same nodes.
    - Examples are drawn as small pill nodes below their parent concept.

Korean labels are supported by using a CJK-capable font if available
on the system; otherwise we fall back to DejaVu (which shows tofu for
Korean) but the raw label strings are preserved in the PNG metadata.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend for server rendering

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib import font_manager

from src.models.concept_map import ConceptMap
from src.services.concept_maps.novak_scoring import (
    HierarchyResult,
    compute_hierarchy,
)

logger = logging.getLogger(__name__)

# Prefer fonts that support Hangul if installed on the host.
_PREFERRED_KR_FONTS = (
    "NanumGothic",
    "Noto Sans CJK KR",
    "Noto Sans KR",
    "Malgun Gothic",
    "AppleGothic",
    "UnDotum",
)


def _pick_font() -> str | None:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in _PREFERRED_KR_FONTS:
        if candidate in available:
            return candidate
    return None


def _apply_korean_font() -> None:
    font_name = _pick_font()
    if font_name:
        matplotlib.rcParams["font.family"] = font_name
    matplotlib.rcParams["axes.unicode_minus"] = False


def _layout_by_level(
    concept_map: ConceptMap, hierarchy: HierarchyResult
) -> dict[str, tuple[float, float]]:
    """Assign (x, y) so nodes stack by level. Isolated nodes go to their own row."""

    by_level: dict[int, list[str]] = {}
    for cid, lvl in hierarchy.concept_levels.items():
        by_level.setdefault(lvl, []).append(cid)

    # Isolated concepts -> a dedicated "level 0" row at the very top right.
    if hierarchy.isolated_concepts:
        by_level.setdefault(0, []).extend(hierarchy.isolated_concepts)

    pos: dict[str, tuple[float, float]] = {}
    if not by_level:
        return pos

    max_cols = max(len(nodes) for nodes in by_level.values())

    # y grows downward (more negative) as level increases to mimic a tree.
    for level, nodes in by_level.items():
        n = len(nodes)
        y = -float(level)
        for idx, cid in enumerate(sorted(nodes)):
            # Evenly spread across a [0, max_cols-1] span.
            x = (idx + 1) * (max_cols + 1) / (n + 1)
            pos[cid] = (x, y)
    return pos


def render_concept_map_png(
    concept_map: ConceptMap,
    hierarchy: HierarchyResult | None = None,
    *,
    title: str | None = None,
    out_path: str | Path | None = None,
    dpi: int = 140,
) -> bytes:
    """Render the concept map to PNG bytes; optionally write to `out_path`.

    Returns the PNG binary so callers can embed it in a PDF directly.
    """

    _apply_korean_font()
    h = hierarchy if hierarchy is not None else compute_hierarchy(concept_map)

    graph: nx.DiGraph = nx.DiGraph()
    labels: dict[str, str] = {}
    for c in concept_map.concepts:
        graph.add_node(c.id)
        labels[c.id] = c.label

    prop_edges: list[tuple[str, str, str]] = []
    concept_ids = set(labels.keys())
    for p in concept_map.propositions:
        if p.from_id in concept_ids and p.to_id in concept_ids:
            graph.add_edge(p.from_id, p.to_id)
            prop_edges.append((p.from_id, p.to_id, p.linking_phrase))

    cross_edges: list[tuple[str, str, str]] = []
    for cl in concept_map.cross_links:
        if cl.from_id in concept_ids and cl.to_id in concept_ids:
            cross_edges.append((cl.from_id, cl.to_id, cl.linking_phrase))

    pos = _layout_by_level(concept_map, h)

    # Figure sized to roughly fit the map; min/max bounds keep tiny/huge maps readable.
    max_cols = max((len(v) for v in _group_by_level(h).values()), default=3)
    n_levels = max(h.max_level, 1) + (1 if h.isolated_concepts else 0)
    width = max(6.0, min(16.0, max_cols * 1.8))
    height = max(4.0, min(14.0, n_levels * 1.6))

    fig, ax = plt.subplots(figsize=(width, height))
    if title:
        ax.set_title(title, fontsize=14)
    ax.axis("off")

    # Nodes
    if pos:
        nx.draw_networkx_nodes(
            graph,
            pos,
            ax=ax,
            node_color="#F3F6FD",
            edgecolors="#4A6CF7",
            linewidths=1.6,
            node_size=2400,
        )
        nx.draw_networkx_labels(graph, pos, labels=labels, ax=ax, font_size=9)

    # Proposition edges (solid, dark)
    if prop_edges:
        nx.draw_networkx_edges(
            graph,
            pos,
            edgelist=[(f, t) for f, t, _ in prop_edges],
            ax=ax,
            edge_color="#2F3E5F",
            arrows=True,
            arrowstyle="-|>",
            arrowsize=14,
            width=1.3,
            connectionstyle="arc3,rad=0.05",
        )
        edge_label_map = {(f, t): lbl for f, t, lbl in prop_edges}
        nx.draw_networkx_edge_labels(
            graph,
            pos,
            edge_labels=edge_label_map,
            ax=ax,
            font_size=7,
            rotate=False,
            bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.8},
        )

    # Cross-links (dashed, red) drawn on a separate mini-graph so their labels
    # don't collide with proposition labels.
    if cross_edges:
        cross_graph: nx.DiGraph = nx.DiGraph()
        cross_graph.add_nodes_from(graph.nodes)
        cross_graph.add_edges_from((f, t) for f, t, _ in cross_edges)
        nx.draw_networkx_edges(
            cross_graph,
            pos,
            ax=ax,
            edge_color="#E04747",
            style="dashed",
            arrows=True,
            arrowstyle="-|>",
            arrowsize=14,
            width=1.2,
            connectionstyle="arc3,rad=-0.25",
        )
        cross_label_map = {(f, t): lbl for f, t, lbl in cross_edges}
        nx.draw_networkx_edge_labels(
            cross_graph,
            pos,
            edge_labels=cross_label_map,
            ax=ax,
            font_size=7,
            rotate=False,
            font_color="#A02020",
            bbox={"boxstyle": "round,pad=0.2", "fc": "#FFF1F1", "ec": "none", "alpha": 0.85},
        )

    # Examples as small tag nodes below their parent concept.
    if concept_map.examples and pos:
        ex_texts: list[str] = []
        for i, ex in enumerate(concept_map.examples):
            parent = pos.get(ex.concept_id)
            if parent is None:
                continue
            ex_x = parent[0] + 0.25
            ex_y = parent[1] - 0.5
            ax.annotate(
                ex.text,
                xy=parent,
                xytext=(ex_x, ex_y),
                fontsize=7,
                ha="left",
                va="top",
                bbox={
                    "boxstyle": "round,pad=0.3",
                    "fc": "#FFF9DB",
                    "ec": "#C6A300",
                    "lw": 0.8,
                },
                arrowprops={"arrowstyle": "-", "color": "#C6A300", "lw": 0.6},
            )
            ex_texts.append(ex.text)

    # Legend
    legend_handles = [
        mpatches.Patch(color="#2F3E5F", label="명제(proposition)"),
        mpatches.Patch(color="#E04747", label="교차연결(cross-link)"),
        mpatches.Patch(color="#C6A300", label="예시(example)"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=8, frameon=True)

    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    data = buf.getvalue()

    if out_path is not None:
        Path(out_path).write_bytes(data)
    return data


def _group_by_level(hierarchy: HierarchyResult) -> dict[int, list[str]]:
    grouped: dict[int, list[str]] = {}
    for cid, lvl in hierarchy.concept_levels.items():
        grouped.setdefault(lvl, []).append(cid)
    return grouped
