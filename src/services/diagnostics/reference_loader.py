"""Load reference materials (markdown / PDF) from configs/reference_materials/.

Instructor-uploaded theory documents are extracted to plain text and injected
into diagnostic prompts as the "참고 이론 자료" block.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_REF_DIR = Path("configs/reference_materials")
MAX_CHARS_PER_MATERIAL = 8000  # keep prompts reasonable
SUPPORTED_EXTS = {".md", ".markdown", ".txt", ".pdf"}


class ReferenceMaterialError(ValueError):
    """Raised when a reference material cannot be loaded."""


@dataclass
class ReferenceMaterial:
    filename: str
    title: str
    text: str
    truncated: bool


def _extract_pdf_text(path: Path) -> str:
    try:
        import pypdf
    except ImportError as exc:  # pragma: no cover
        raise ReferenceMaterialError(
            "pypdf not installed. Run `pip install -r requirements.txt`."
        ) from exc

    try:
        reader = pypdf.PdfReader(str(path))
    except Exception as exc:
        raise ReferenceMaterialError(f"PDF open failed for {path}: {exc}") from exc

    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as exc:  # pragma: no cover - page-level parser errors
            logger.warning("PDF page extraction failed in %s: %s", path.name, exc)
    return "\n\n".join(parts)


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8")
    if ext == ".pdf":
        return _extract_pdf_text(path)
    raise ReferenceMaterialError(f"Unsupported reference file type: {path.suffix} ({path})")


def _derive_title(path: Path, text: str) -> str:
    """Prefer the first markdown H1, else the file stem."""

    for line in text.splitlines()[:20]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("# ").strip()
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def load_reference_material(
    filename: str, ref_dir: Path = DEFAULT_REF_DIR
) -> ReferenceMaterial:
    """Load a single reference file by filename (relative to ref_dir)."""

    path = Path(ref_dir) / filename
    if not path.exists():
        raise ReferenceMaterialError(f"Reference material not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise ReferenceMaterialError(f"Unsupported extension for reference: {path.suffix}")

    text = _extract_text(path).strip()
    truncated = False
    if len(text) > MAX_CHARS_PER_MATERIAL:
        text = text[:MAX_CHARS_PER_MATERIAL] + "\n\n...(이하 생략)"
        truncated = True

    return ReferenceMaterial(
        filename=filename,
        title=_derive_title(path, text),
        text=text,
        truncated=truncated,
    )


def load_reference_materials(
    filenames: list[str], ref_dir: Path = DEFAULT_REF_DIR
) -> list[ReferenceMaterial]:
    """Load multiple reference files. Missing files are logged and skipped."""

    results: list[ReferenceMaterial] = []
    for fn in filenames:
        try:
            results.append(load_reference_material(fn, ref_dir))
        except ReferenceMaterialError as exc:
            logger.warning("Skipping reference material '%s': %s", fn, exc)
    return results


def list_reference_materials(ref_dir: Path = DEFAULT_REF_DIR) -> list[str]:
    """Return filenames of all reference materials present in ref_dir."""

    dir_path = Path(ref_dir)
    if not dir_path.is_dir():
        return []
    names: list[str] = []
    for p in sorted(dir_path.iterdir()):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            names.append(p.name)
    return names


def format_materials_block(materials: list[ReferenceMaterial]) -> str:
    """Format loaded materials into a single string for prompt injection."""

    if not materials:
        return "(참고 자료 없음)"
    blocks = []
    for m in materials:
        blocks.append(f"### [{m.title}] ({m.filename})\n{m.text}")
    return "\n\n---\n\n".join(blocks)
