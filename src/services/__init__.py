"""Services layer: prompt engine, Claude wrapper, session orchestration."""

from src.services.claude_service import ClaudeService
from src.services.instructor_service import (
    InstructorAuthError,
    SessionSummary,
    UnitSummary,
    admin_enabled,
    delete_reference,
    delete_unit,
    get_report_paths_for_session,
    list_sessions,
    list_units,
    rerun_analysis,
    reset_session_to_in_progress,
    save_reference_upload,
    save_unit_config,
    verify_instructor_password,
)
from src.services.scaffolding_engine import build_system_prompt, build_unit_layer
from src.services.session_manager import (
    AuthenticationError,
    LoginResult,
    PreMapResult,
    SessionLockedError,
    SessionManager,
    StepViolationError,
)

__all__ = [
    "ClaudeService",
    "build_system_prompt",
    "build_unit_layer",
    "SessionManager",
    "LoginResult",
    "PreMapResult",
    "AuthenticationError",
    "SessionLockedError",
    "StepViolationError",
    "InstructorAuthError",
    "UnitSummary",
    "SessionSummary",
    "admin_enabled",
    "delete_reference",
    "delete_unit",
    "list_sessions",
    "list_units",
    "get_report_paths_for_session",
    "rerun_analysis",
    "reset_session_to_in_progress",
    "save_reference_upload",
    "save_unit_config",
    "verify_instructor_password",
]
