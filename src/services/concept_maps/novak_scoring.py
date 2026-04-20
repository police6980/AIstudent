"""Automatic hierarchy inference + Novak-style scoring for concept maps.

Hierarchy inference (without student input):
    1. Build a directed graph from propositions (cross_links not used for
       hierarchy — they deliberately span branches).
    2. Condense strongly connected components so any cycles become a single
       super-node and the graph becomes a DAG.
    3. Roots = nodes with in-degree 0 in the DAG. (If everything is cyclic,
       the whole graph becomes a single SCC and is treated as Level 1.)
    4. Level = length of the longest path from any root to the node.
       Longest (not shortest) path better matches the pedagogical intuition
       that a concept reachable through several specializations "sits deeper".

Novak & Gowin (1984) scoring:
    total = propositions * w_prop
          + hierarchy_levels * w_hier
          + cross_links * w_cross
          + examples * w_ex
          + isolated_concepts * w_isolated_penalty
Weights are read from the concept_map_diagnosis diagnostic YAML so instructors
can adjust them without changing code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from src.models.concept_map import ConceptMap, ConceptMapScore

# Defaults come from Novak & Gowin (1984). Instructor-edited diagnostics
# YAML can override any of these.
DEFAULT_WEIGHTS: dict[str, float] = {
    "proposition": 1.0,
    "hierarchy_level": 5.0,
    "cross_link": 10.0,
    "example": 1.0,
    "misconception_penalty": -5.0,
    "isolated_concept_penalty": -2.0,
}


@dataclass
class HierarchyResult:
    """Output of compute_hierarchy(): per-concept level + structural summary."""

    concept_levels: dict[str, int] = field(default_factory=dict)  # concept_id -> level (1-based)
    roots: list[str] = field(default_factory=list)                # root concept ids
    max_level: int = 0                                             # deepest level found
    isolated_concepts: list[str] = field(default_factory=list)     # concepts with no edges
    cycles_present: bool = False                                   # whether we collapsed any SCC


def _build_proposition_graph(concept_map: ConceptMap) -> nx.DiGraph:
    """Directed graph using only propositions (cross_links excluded)."""

    g: nx.DiGraph = nx.DiGraph()
    for c in concept_map.concepts:
        g.add_node(c.id, label=c.label)
    for p in concept_map.propositions:
        if p.from_id in g and p.to_id in g:
            g.add_edge(p.from_id, p.to_id, linking=p.linking_phrase)
    return g


def compute_hierarchy(concept_map: ConceptMap) -> HierarchyResult:
    """Infer per-concept hierarchy level + structural summary.

    Roots are in-degree-0 nodes in the condensed DAG. Level = longest-path
    depth from the nearest root. Isolated concepts are reported but not
    assigned to a level.
    """

    g = _build_proposition_graph(concept_map)
    result = HierarchyResult()

    if g.number_of_nodes() == 0:
        return result

    # Isolated = no propositions touching them (cross-links still count so
    # a concept connected only by a cross-link is NOT isolated).
    cross_touched: set[str] = set()
    for cl in concept_map.cross_links:
        cross_touched.add(cl.from_id)
        cross_touched.add(cl.to_id)
    for example in concept_map.examples:
        cross_touched.add(example.concept_id)

    for node in g.nodes:
        if g.in_degree(node) == 0 and g.out_degree(node) == 0 and node not in cross_touched:
            result.isolated_concepts.append(node)

    # Condense cycles into SCCs to get a DAG.
    scc = list(nx.strongly_connected_components(g))
    result.cycles_present = any(len(s) > 1 for s in scc)
    condensed = nx.condensation(g, scc)

    # Map each original node -> SCC index (= condensed node id).
    node_to_scc: dict[str, int] = {}
    for idx, members in enumerate(scc):
        for m in members:
            node_to_scc[m] = idx

    # Longest-path depth from any root in the DAG.
    depths: dict[int, int] = {}
    for node in nx.topological_sort(condensed):
        preds = list(condensed.predecessors(node))
        if not preds:
            depths[node] = 1
        else:
            depths[node] = max(depths[p] for p in preds) + 1

    # Roots and levels back-mapped to original concept ids.
    for scc_node in condensed.nodes:
        if condensed.in_degree(scc_node) == 0:
            for m in scc[scc_node]:
                result.roots.append(m)

    for concept in concept_map.concepts:
        if concept.id in result.isolated_concepts:
            continue
        if concept.id in node_to_scc:
            result.concept_levels[concept.id] = depths[node_to_scc[concept.id]]

    if result.concept_levels:
        result.max_level = max(result.concept_levels.values())

    return result


def _resolve_weights(weights_override: dict | None) -> dict[str, float]:
    if not weights_override:
        return dict(DEFAULT_WEIGHTS)
    merged = dict(DEFAULT_WEIGHTS)
    for k, v in weights_override.items():
        try:
            merged[k] = float(v)
        except (TypeError, ValueError):
            continue
    return merged


def score_concept_map(
    concept_map: ConceptMap,
    hierarchy: HierarchyResult | None = None,
    weights: dict | None = None,
    misconception_count: int = 0,
) -> ConceptMapScore:
    """Compute Novak-style score.

    Args:
        concept_map: the student's map.
        hierarchy: precomputed HierarchyResult (to avoid recomputation). If
            None, it is recomputed here.
        weights: dict of weight overrides pulled from the concept_map_diagnosis
            YAML. Falls back to Novak & Gowin (1984) defaults per missing key.
        misconception_count: number of misconceptions detected in the map
            (passed in by whichever diagnostic ran this scoring). Multiplied
            by the negative `misconception_penalty` weight.
    """

    h = hierarchy if hierarchy is not None else compute_hierarchy(concept_map)
    w = _resolve_weights(weights)

    # A proposition is "valid" if both endpoints exist. The pydantic layer
    # already rejects empty linking phrases, so validity here means
    # reference-correctness.
    concept_ids = {c.id for c in concept_map.concepts}
    valid_prop = sum(
        1 for p in concept_map.propositions if p.from_id in concept_ids and p.to_id in concept_ids
    )
    valid_cross = sum(
        1 for cl in concept_map.cross_links if cl.from_id in concept_ids and cl.to_id in concept_ids
    )

    total = (
        valid_prop * w["proposition"]
        + h.max_level * w["hierarchy_level"]
        + valid_cross * w["cross_link"]
        + len(concept_map.examples) * w["example"]
        + len(h.isolated_concepts) * w["isolated_concept_penalty"]
        + misconception_count * w["misconception_penalty"]
    )

    return ConceptMapScore(
        proposition_count=len(concept_map.propositions),
        valid_proposition_count=valid_prop,
        max_hierarchy_level=h.max_level,
        cross_link_count=valid_cross,
        example_count=len(concept_map.examples),
        isolated_concept_count=len(h.isolated_concepts),
        total=round(total, 2),
        weights_used=w,
    )
