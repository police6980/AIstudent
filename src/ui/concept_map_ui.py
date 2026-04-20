"""Reusable Gradio component for student concept-map input.

The student fills four blocks:
    1) 개념 목록 — one concept per line (ids auto-assigned c1, c2, ...)
    2) 명제       — "from개념 | 연결어 | to개념" per line, by label
    3) 교차연결   — same format as propositions (student flags as cross-branch)
    4) 예시       — "개념 | 예시 본문" per line

The helper build_concept_map_from_inputs(...) turns these four text blocks
into a validated `ConceptMap` so the rest of the pipeline stays strict.

The UI also includes a live "시각화 미리보기" button so the student can
check their map before submitting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import gradio as gr
from PIL import Image

from src.models.concept_map import (
    Concept,
    ConceptMap,
    CrossLink,
    Example,
    Proposition,
)
from src.services.concept_maps import (
    compute_hierarchy,
    render_concept_map_png,
    score_concept_map,
)

logger = logging.getLogger(__name__)


class ConceptMapParseError(ValueError):
    """Raised when a student's free-text input can't be turned into a ConceptMap."""


def _parse_concepts_block(text: str) -> list[Concept]:
    """One concept per line. Ids are auto-assigned: c1, c2, c3, ..."""

    concepts: list[Concept] = []
    seen_labels: set[str] = set()
    for i, raw in enumerate((text or "").splitlines(), start=1):
        label = raw.strip()
        if not label or label.startswith("#"):
            continue
        if label.casefold() in seen_labels:
            # Duplicate concept label — silently skip later duplicates
            continue
        seen_labels.add(label.casefold())
        concepts.append(Concept(id=f"c{i}", label=label))
    return concepts


def _label_to_id(concepts: list[Concept]) -> dict[str, str]:
    return {c.label.casefold(): c.id for c in concepts}


def _parse_edge_block(
    text: str,
    concepts: list[Concept],
    *,
    kind: str,
) -> tuple[list[Proposition] | list[CrossLink], list[str]]:
    """Shared parser for propositions + cross-links.

    Each line: "from_label | linking_phrase | to_label"
    Returns (parsed, warnings). Unknown labels are reported as warnings
    and the offending line is skipped rather than raising.
    """

    mapping = _label_to_id(concepts)
    parsed: list = []
    warnings: list[str] = []
    for i, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            warnings.append(f"{kind} {i}행: '|' 로 구분된 3개 요소가 필요해요 — '{line}'")
            continue
        src, linking, dst = parts
        src_id = mapping.get(src.casefold())
        dst_id = mapping.get(dst.casefold())
        if not src_id:
            warnings.append(f"{kind} {i}행: 개념 목록에 없는 시작 개념 '{src}'")
            continue
        if not dst_id:
            warnings.append(f"{kind} {i}행: 개념 목록에 없는 끝 개념 '{dst}'")
            continue
        if src_id == dst_id:
            warnings.append(f"{kind} {i}행: from 과 to 가 같아요 ('{src}')")
            continue
        if not linking:
            warnings.append(f"{kind} {i}행: 연결어가 비었어요")
            continue
        if kind == "명제":
            parsed.append(Proposition(from_id=src_id, to_id=dst_id, linking_phrase=linking))
        else:
            parsed.append(CrossLink(from_id=src_id, to_id=dst_id, linking_phrase=linking))
    return parsed, warnings


def _parse_examples_block(
    text: str, concepts: list[Concept]
) -> tuple[list[Example], list[str]]:
    mapping = _label_to_id(concepts)
    out: list[Example] = []
    warnings: list[str] = []
    for i, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", 1)]
        if len(parts) != 2:
            warnings.append(f"예시 {i}행: '개념 | 예시 내용' 형식이 필요해요 — '{line}'")
            continue
        concept_label, example_text = parts
        concept_id = mapping.get(concept_label.casefold())
        if not concept_id:
            warnings.append(f"예시 {i}행: 개념 목록에 없는 '{concept_label}'")
            continue
        if not example_text:
            warnings.append(f"예시 {i}행: 예시 내용이 비었어요")
            continue
        out.append(Example(concept_id=concept_id, text=example_text))
    return out, warnings


@dataclass
class ParseResult:
    concept_map: ConceptMap
    warnings: list[str]


def build_concept_map_from_inputs(
    concepts_text: str,
    propositions_text: str,
    cross_links_text: str,
    examples_text: str,
) -> ParseResult:
    """Parse the four text blocks into a validated ConceptMap."""

    concepts = _parse_concepts_block(concepts_text)
    if not concepts:
        raise ConceptMapParseError("개념이 최소 1개 이상 필요합니다.")

    propositions, p_warn = _parse_edge_block(propositions_text, concepts, kind="명제")
    cross_links, c_warn = _parse_edge_block(cross_links_text, concepts, kind="교차연결")
    examples, e_warn = _parse_examples_block(examples_text, concepts)

    cmap = ConceptMap(
        concepts=concepts,
        propositions=list(propositions),
        cross_links=list(cross_links),
        examples=examples,
    )
    ref_warn = cmap.validate_references()
    return ParseResult(concept_map=cmap, warnings=p_warn + c_warn + e_warn + ref_warn)


def _score_summary_text(cmap: ConceptMap) -> str:
    h = compute_hierarchy(cmap)
    score = score_concept_map(cmap, hierarchy=h)
    return (
        f"개념 {len(cmap.concepts)}개 · 명제 {score.valid_proposition_count}/{len(cmap.propositions)} · "
        f"교차연결 {score.cross_link_count} · 예시 {score.example_count} · "
        f"위계 최대 Lv {score.max_hierarchy_level} · "
        f"고립 개념 {score.isolated_concept_count} · "
        f"**Novak 점수 {score.total}**"
    )


def _png_to_pil(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data)).convert("RGB")


def build_concept_map_input_block(
    title: str,
    description_md: str,
    submit_label: str,
    state_prefix: str,
) -> dict[str, Any]:
    """Render the reusable concept-map input block inside a Gradio parent Blocks.

    Returns a dict of the component handles the caller needs to wire
    submission callbacks:
        {
            "concepts_in", "propositions_in", "cross_links_in", "examples_in",
            "preview_btn", "submit_btn", "preview_img", "summary_md", "warnings_md"
        }
    """

    gr.Markdown(f"### {title}")
    gr.Markdown(description_md)

    concepts_in = gr.Textbox(
        label="개념 목록 — 한 줄에 하나",
        placeholder="예)\n광합성\n빛\n물\n이산화탄소\n엽록체\n포도당\n산소",
        lines=8,
    )
    propositions_in = gr.Textbox(
        label="명제 — 한 줄에 하나  (시작개념 | 연결어 | 끝개념)",
        placeholder="예)\n광합성 | 의 조건은 | 빛\n광합성 | 이 일어나는 장소는 | 엽록체",
        lines=8,
    )
    cross_links_in = gr.Textbox(
        label="교차연결 — 가지 사이를 잇는 특별한 연결 (시작 | 연결어 | 끝)",
        placeholder="예)\n엽록체 | 가 흡수하는 | 빛",
        lines=4,
    )
    examples_in = gr.Textbox(
        label="예시 — 한 줄에 하나  (개념 | 예시 내용)",
        placeholder="예)\n포도당 | 설탕은 식물이 만든 포도당의 변형\n빛 | 태양광",
        lines=4,
    )

    with gr.Row():
        preview_btn = gr.Button("🔍 미리보기")
        submit_btn = gr.Button(submit_label, variant="primary")

    summary_md = gr.Markdown("")
    warnings_md = gr.Markdown("")
    preview_img = gr.Image(label="개념도 시각화", type="pil", interactive=False)

    def on_preview(
        concepts_text: str,
        propositions_text: str,
        cross_links_text: str,
        examples_text: str,
    ) -> tuple[Any, str, str]:
        try:
            result = build_concept_map_from_inputs(
                concepts_text, propositions_text, cross_links_text, examples_text
            )
        except ConceptMapParseError as exc:
            return None, "", f"⚠️ {exc}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Concept map preview failed")
            return None, "", f"⚠️ 미리보기 실패: {exc}"

        summary = _score_summary_text(result.concept_map)
        warnings = (
            "ℹ️ 경고:\n" + "\n".join(f"- {w}" for w in result.warnings)
            if result.warnings
            else "✅ 참조 오류 없음."
        )
        try:
            png = render_concept_map_png(result.concept_map, title=title)
            img = _png_to_pil(png)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Concept map visualization failed")
            return None, summary, f"{warnings}\n\n⚠️ 시각화 실패: {exc}"
        return img, summary, warnings

    preview_btn.click(
        on_preview,
        inputs=[concepts_in, propositions_in, cross_links_in, examples_in],
        outputs=[preview_img, summary_md, warnings_md],
    )

    return {
        "concepts_in": concepts_in,
        "propositions_in": propositions_in,
        "cross_links_in": cross_links_in,
        "examples_in": examples_in,
        "preview_btn": preview_btn,
        "submit_btn": submit_btn,
        "preview_img": preview_img,
        "summary_md": summary_md,
        "warnings_md": warnings_md,
        "state_prefix": state_prefix,
    }
