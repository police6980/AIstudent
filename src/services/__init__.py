"""Services layer: prompt engine, Claude wrapper, session orchestration."""

from src.services.claude_service import ClaudeService
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
]
