"""Thin wrapper around the Anthropic Claude API."""

from __future__ import annotations

import logging
from typing import Optional

from src.config.settings import Settings, get_settings
from src.models.enums import Speaker
from src.models.schemas import Turn

logger = logging.getLogger(__name__)


class ClaudeServiceError(RuntimeError):
    """Raised when the Claude API call cannot be completed."""


def _turns_to_messages(turns: list[Turn]) -> list[dict]:
    """Convert stored Turn list into Anthropic Messages API format."""

    messages: list[dict] = []
    for t in turns:
        role = "user" if t.speaker == Speaker.STUDENT else "assistant"
        messages.append({"role": role, "content": t.content})
    return messages


class ClaudeService:
    """Wrapper responsible for calling Claude with a system prompt + history."""

    def __init__(self, settings: Optional[Settings] = None, client=None):
        self._settings = settings or get_settings()
        self._client = client  # lazy init — see _get_client()

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._settings.anthropic_api_key:
            raise ClaudeServiceError(
                "ANTHROPIC_API_KEY is not set. Configure it in .env before calling Claude."
            )
        try:
            import anthropic  # imported lazily to avoid hard dep at import time
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ClaudeServiceError(
                "anthropic SDK not installed. Run `pip install -r requirements.txt`."
            ) from exc
        self._client = anthropic.Anthropic(api_key=self._settings.anthropic_api_key)
        return self._client

    def generate_response(
        self,
        system_prompt: str,
        history: list[Turn],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Call Claude and return the assistant text reply.

        `history` includes all prior turns (both student and AI) in chronological order.
        If history is empty, Claude is prompted with a minimal user message
        asking it to greet the student (per the Layer 3 instruction).
        """

        client = self._get_client()
        messages = _turns_to_messages(history)

        if not messages:
            # No prior turns: ask Claude to open the conversation in-character.
            messages = [
                {
                    "role": "user",
                    "content": "(세션 시작) 학생에게 페르소나로서 먼저 인사하며, "
                    "오늘 배운 내용을 너에게 설명해달라고 자연스럽게 말을 걸어줘.",
                }
            ]

        kwargs = {
            "model": self._settings.claude_model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        }
        try:
            response = client.messages.create(temperature=temperature, **kwargs)
        except Exception as exc:
            msg = str(exc).lower()
            if "temperature" in msg and ("deprecated" in msg or "not" in msg):
                logger.info("Retrying dialogue call without temperature.")
                try:
                    response = client.messages.create(**kwargs)
                except Exception as exc2:
                    logger.exception("Claude API call failed on retry")
                    raise ClaudeServiceError(f"Claude API call failed: {exc2}") from exc2
            else:
                logger.exception("Claude API call failed")
                raise ClaudeServiceError(f"Claude API call failed: {exc}") from exc

        # Anthropic returns a list of content blocks; concatenate text blocks.
        chunks: list[str] = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                chunks.append(text)
        reply = "".join(chunks).strip()
        if not reply:
            raise ClaudeServiceError("Claude returned an empty response.")
        return reply
