"""Instructor-side services: auth, unit CRUD, session browsing.

Used by the instructor UI (?admin=true). Student flows never call this.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import select

from src.config.settings import get_settings
from src.config.unit_config import load_unit_config
from src.db.database import get_session_factory
from src.models.db_models import SessionRow, TurnRow
from src.models.enums import SessionStatus
from src.models.schemas import UnitConfig

logger = logging.getLogger(__name__)

CONFIGS_DIR = Path("configs")


class InstructorAuthError(RuntimeError):
    """Raised when the admin password is wrong or not configured."""


def verify_instructor_password(attempt: str) -> bool:
    """Compare a submitted password against INSTRUCTOR_PASSWORD env.

    Returns False if the env var is empty or unset — the admin page is
    effectively disabled unless the instructor configures a password.
    """

    configured = get_settings().instructor_password
    if not configured:
        return False
    return (attempt or "") == configured


def admin_enabled() -> bool:
    """True when INSTRUCTOR_PASSWORD is configured (non-empty)."""

    configured = get_settings().instructor_password
    return bool(configured and configured.strip())


# ---- Unit CRUD ---------------------------------------------------------


@dataclass
class UnitSummary:
    """Lightweight row for the instructor unit table."""

    filename: str
    unit_code: str
    unit_name: str
    persona_name: str
    student_count: int


def list_units(configs_dir: Path = CONFIGS_DIR) -> list[UnitSummary]:
    """Return summaries of all real (non-example) unit YAMLs."""

    dir_path = Path(configs_dir)
    if not dir_path.is_dir():
        return []

    out: list[UnitSummary] = []
    for p in sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml")):
        try:
            cfg = load_unit_config(p)
        except Exception as exc:  # noqa: BLE001 - any parse error should just skip
            logger.warning("Skipping unreadable unit YAML %s: %s", p, exc)
            continue
        out.append(
            UnitSummary(
                filename=p.name,
                unit_code=cfg.unit_code,
                unit_name=cfg.unit_name,
                persona_name=cfg.persona_name,
                student_count=len(cfg.student_accounts),
            )
        )
    return out


def save_unit_config(config: UnitConfig, configs_dir: Path = CONFIGS_DIR) -> Path:
    """Write a UnitConfig to configs/<unit_code>.yaml (overwrites existing)."""

    dir_path = Path(configs_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"{config.unit_code}.yaml"
    payload = config.model_dump(mode="json")
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def delete_unit(filename: str, configs_dir: Path = CONFIGS_DIR) -> None:
    """Delete a unit YAML. Also removes its sidecar .accounts.txt if present."""

    dir_path = Path(configs_dir)
    path = dir_path / filename
    if path.exists() and path.is_file():
        path.unlink()
    sidecar = path.with_suffix(".accounts.txt")
    if sidecar.exists():
        sidecar.unlink()


def save_reference_upload(src_path: str | Path, dest_filename: str) -> Path:
    """Copy an uploaded file into configs/reference_materials/.

    dest_filename is the final basename (e.g. 'vygotsky_paper.pdf').
    """

    src = Path(src_path)
    dest_dir = Path("configs/reference_materials")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / dest_filename
    shutil.copyfile(src, dest)
    return dest


def delete_reference(filename: str) -> None:
    """Remove a reference material file."""

    path = Path("configs/reference_materials") / filename
    if path.exists() and path.is_file():
        path.unlink()


# ---- Session browsing --------------------------------------------------


@dataclass
class SessionSummary:
    session_id: str
    unit_code: str
    student_id: str
    status: SessionStatus
    start_time: datetime
    end_time: Optional[datetime]
    turn_count: int


def list_sessions(unit_code: Optional[str] = None) -> list[SessionSummary]:
    """List recent sessions (optionally filtered by unit_code)."""

    factory = get_session_factory()
    with factory() as db:
        stmt = select(SessionRow).order_by(SessionRow.start_time.desc())
        if unit_code:
            stmt = stmt.where(SessionRow.unit_code == unit_code)
        rows = db.execute(stmt).scalars().all()

        out: list[SessionSummary] = []
        for r in rows:
            turn_count = db.execute(
                select(TurnRow.id).where(TurnRow.session_id == r.id)
            ).all()
            out.append(
                SessionSummary(
                    session_id=r.id,
                    unit_code=r.unit_code,
                    student_id=r.student_id,
                    status=SessionStatus(r.status),
                    start_time=r.start_time,
                    end_time=r.end_time,
                    turn_count=len(turn_count),
                )
            )
    return out


def reset_session_to_in_progress(session_id: str) -> None:
    """Instructor override: reopen a completed session so the student can resume."""

    factory = get_session_factory()
    with factory() as db:
        row = db.get(SessionRow, session_id)
        if row is None:
            raise LookupError(f"Session not found: {session_id}")
        row.status = SessionStatus.IN_PROGRESS.value
        row.end_time = None
        db.commit()


def rerun_analysis(session_id: str) -> int:
    """Re-run the analysis pipeline + PDF generation on a completed session.

    Returns the number of analyzer errors encountered (0 = perfect).
    Imports are lazy so the instructor service stays free of heavy deps
    until someone actually asks for a rerun.
    """

    from src.db.repository import SessionRepository
    from src.services.analysis import run_full_analysis
    from src.services.pdf import generate_reports_for_session

    repo = SessionRepository()
    bundle = run_full_analysis(session_id, repo=repo)
    try:
        generate_reports_for_session(session_id, repo=repo)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF regeneration failed for %s: %s", session_id, exc)
    return len(bundle.errors)


def get_report_paths_for_session(session_id: str):
    """Return (summary_path, detail_path) or (None, None) for a session."""

    from pathlib import Path

    from src.config.settings import get_settings
    from src.db.repository import SessionRepository

    row = SessionRepository().get_session(session_id)
    if row is None:
        return None, None
    settings = get_settings()
    candidates = list(
        Path(settings.report_dir).glob(
            f"{row.unit_code}_{row.student_id}_{session_id[:8]}"
        )
    )
    if not candidates:
        return None, None
    out_dir = candidates[0]
    summary = out_dir / "summary.pdf"
    detail = out_dir / "detail.pdf"
    if not summary.exists() or not detail.exists():
        return None, None
    return str(summary), str(detail)
