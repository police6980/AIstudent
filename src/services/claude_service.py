"""Thin wrapper around the Anthropic Claude API."""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

from src.config.settings import Settings, get_settings
from src.models.enums import Speaker
from src.models.schemas import Turn

logger = logging.getLogger(__name__)

# Retry policy for transient server-side errors (529 Overloaded, 5xx).
_TRANSIENT_MAX_RETRIES = 3
_TRANSIENT_BASE_DELAY_SEC = 1.5  # grows exponentially: 1.5, 3, 6


def _is_overloaded(exc: Exception) -> bool:
    """True for 529 overloaded or generic 5xx retryables."""

    msg = str(exc).lower()
    if "overload" in msg or "529" in msg:
        return True
    code = getattr(exc, "status_code", None)
    if isinstance(code, int) and 500 <= code < 600 and code != 504:
        return True
    return False


def _is_context_too_long(exc: Exception) -> bool:
    """True for the 'context reduction is suggested' 422 error."""

    msg = str(exc).lower()
    return "context" in msg and ("reduc" in msg or "too long" in msg or "exceed" in msg)


def _is_temperature_rejected(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "temperature" in msg and ("deprecated" in msg or "not" in msg)


class ClaudeServiceError(RuntimeError):
    """Raised when the Claude API call cannot be completed."""


def _turns_to_messages(turns: list[Turn]) -> list[dict]:
    """Convert stored Turn list into Anthropic Messages API format."""

    messages: list[dict] = []
    for t in turns:
        role = "user" if t.speaker == Speaker.STUDENT else "assistant"
        messages.append({"role": role, "content": t.content})
    return messages


# Weak registry of live ClaudeService instances so we can clear their
# cached Anthropic clients when the instructor updates the API key at
# runtime from the admin UI.
import weakref as _weakref

_LIVE_SERVICES: "_weakref.WeakSet[ClaudeService]" = _weakref.WeakSet()


def reset_all_claude_clients() -> None:
    """Drop every live ClaudeService's cached client, forcing re-auth on next call."""

    for svc in list(_LIVE_SERVICES):
        svc._client = None  # noqa: SLF001
        svc._settings = None  # noqa: SLF001


class ClaudeService:
    """Wrapper responsible for calling Claude with a system prompt + history."""

    def __init__(self, settings: Optional[Settings] = None, client=None):
        self._settings = settings or get_settings()
        self._client = client  # lazy init — see _get_client()
        _LIVE_SERVICES.add(self)

    def _fresh_settings(self) -> Settings:
        """Always re-read settings so runtime API key updates take effect."""

        self._settings = get_settings()
        return self._settings

    def _get_client(self):
        if self._client is not None:
            return self._client
        # Re-check settings so a runtime-provided API key is picked up.
        self._fresh_settings()
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

    def _call_with_retry(
        self,
        client,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        enable_web_search: bool = False,
    ):
        """Call client.messages.create with:
        - retry on 529 Overloaded / transient 5xx (exponential backoff)
        - retry without temperature if the model rejects it
        - retry with halved history on 422 context-too-long
        - retry without web_search tool if the account rejects it
        """

        # Work on a local copy so we can halve it if needed.
        current_messages = list(messages)
        use_temperature = True
        use_web_search = enable_web_search
        last_exc: Exception | None = None

        for attempt in range(_TRANSIENT_MAX_RETRIES + 1):
            kwargs = {
                "model": self._settings.claude_model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": current_messages,
            }
            if use_temperature:
                kwargs["temperature"] = temperature
            if use_web_search:
                # Anthropic server-side web search tool.
                # Kept to a tight cap to avoid ballooning latency/cost per turn.
                kwargs["tools"] = [
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 2,
                    }
                ]

            try:
                return client.messages.create(**kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc

                msg_str = str(exc).lower()
                if use_web_search and (
                    "web_search" in msg_str
                    or "tool" in msg_str
                    or "unknown field" in msg_str
                ):
                    logger.warning("Web search tool rejected; retrying without it.")
                    use_web_search = False
                    continue

                if _is_temperature_rejected(exc) and use_temperature:
                    logger.info("Model rejected temperature; retrying without it.")
                    use_temperature = False
                    continue

                if _is_context_too_long(exc) and len(current_messages) > 4:
                    # Keep the last 40% of turns (always retain at least the final 4).
                    keep = max(4, len(current_messages) * 2 // 5)
                    logger.warning(
                        "Context too long; trimming history %d -> %d turns and retrying.",
                        len(current_messages), keep,
                    )
                    current_messages = current_messages[-keep:]
                    continue

                if _is_overloaded(exc) and attempt < _TRANSIENT_MAX_RETRIES:
                    delay = _TRANSIENT_BASE_DELAY_SEC * (2 ** attempt)
                    delay += random.uniform(0, delay * 0.3)  # jitter
                    logger.warning(
                        "Claude overloaded (attempt %d/%d). Waiting %.1fs then retrying.",
                        attempt + 1, _TRANSIENT_MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue

                logger.exception("Claude API call failed")
                raise ClaudeServiceError(f"Claude API call failed: {exc}") from exc

        # Exhausted retries
        logger.error("Claude API exhausted retries.")
        raise ClaudeServiceError(
            f"Claude API call failed after retries: {last_exc}"
        ) from last_exc

    def generate_response(
        self,
        system_prompt: str,
        history: list[Turn],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        enable_web_search: bool = False,
    ) -> str:
        """Call Claude and return the assistant text reply.

        `history` includes all prior turns (both student and AI) in chronological order.
        If history is empty, Claude is prompted with a minimal user message
        asking it to greet the student (per the Layer 3 instruction).

        If `enable_web_search=True`, the server-side web_search tool is offered
        to Claude (limited to 2 searches per turn). Opt in per unit via
        UnitConfig.web_search_enabled.
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

        response = self._call_with_retry(
            client,
            system_prompt,
            messages,
            max_tokens,
            temperature,
            enable_web_search=enable_web_search,
        )

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
