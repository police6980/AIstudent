"""Services layer: prompt engine, Claude wrapper, session orchestration."""

from src.services.claude_service import ClaudeService
from src.services.instructor_service import (
    InstructorAuthError,
    SessionSummary,
    UnitSummary,
    admin_enabled,
    delete_reference,
    delete_unit,
    list_sessions,
    list_units,
    reset_session_to_in_progress,
    save_reference_upload,
    save_unit_config,
    verify_instructor_password,
)
from src.services.scaffolding_engine import build_system_prompt, build_unit_layer
from src.services.session_manager import (
    AuthenticationError,
    LoginResult,
    SessionLockedError,
    SessionManager,
)

__all__ = [
    "ClaudeService",
    "build_system_prompt",
    "build_unit_layer",
    "SessionManager",
    "LoginResult",
    "AuthenticationError",
    "SessionLockedError",
    "InstructorAuthError",
    "UnitSummary",
    "SessionSummary",
    "admin_enabled",
    "delete_reference",
    "delete_unit",
    "list_sessions",
    "list_units",
    "reset_session_to_in_progress",
    "save_reference_upload",
    "save_unit_config",
    "verify_instructor_password",
]
