"""Per-provider stub fixtures for LiteLLM dispatch testing.

These minimal stubs synthesise litellm-shaped exceptions and responses for
each supported provider so unit tests can exercise per-provider error
handling without hitting any network. Used by
``tests/test_provider_compat_matrix.py``.

The stubs are deliberately small; they don't wrap the full LiteLLM API
surface. Each builder returns either:
- a LiteLLM exception instance to raise from a mocked acompletion, or
- a synthetic response object shaped like a LiteLLM ModelResponse.

Cross-ref ``docs/provider-compatibility-matrix.md`` for the per-provider
behaviour these stubs encode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import litellm


@dataclass
class _StubChoice:
    message: Any
    finish_reason: str = "stop"


@dataclass
class _StubMessage:
    content: str
    role: str = "assistant"


@dataclass
class _StubUsage:
    prompt_tokens: int = 100
    completion_tokens: int = 50
    total_tokens: int = 150


@dataclass
class StubResponse:
    """Synthetic LiteLLM ModelResponse — only the fields _extract_response reads."""

    choices: list[_StubChoice]
    usage: _StubUsage
    model: str

    @classmethod
    def make(
        cls,
        *,
        content: str = "stub response",
        prompt_tokens: int = 100,
        completion_tokens: int = 50,
        model: str = "gpt-4o",
    ) -> StubResponse:
        return cls(
            choices=[_StubChoice(message=_StubMessage(content=content))],
            usage=_StubUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            model=model,
        )


# ---------------------------------------------------------------------------
# Per-provider rate-limit error builders
# ---------------------------------------------------------------------------


def anthropic_rate_limit() -> litellm.RateLimitError:
    """Anthropic 429 rate_limit_error normalised through LiteLLM."""
    return litellm.RateLimitError(
        message="rate_limit_error: requests per minute exceeded",
        llm_provider="anthropic",
        model="claude-sonnet-4-6",
    )


def openai_rate_limit() -> litellm.RateLimitError:
    """OpenAI 429 rate_limit_exceeded normalised through LiteLLM."""
    return litellm.RateLimitError(
        message="rate_limit_exceeded: 60 RPM cap",
        llm_provider="openai",
        model="gpt-4o",
    )


def gemini_rate_limit() -> litellm.RateLimitError:
    """Gemini 429 RESOURCE_EXHAUSTED — zero-quota free-tier shape."""
    return litellm.RateLimitError(
        message="RESOURCE_EXHAUSTED: project quota exceeded",
        llm_provider="gemini",
        model="gemini-2.0-flash",
    )


def groq_rate_limit() -> litellm.RateLimitError:
    """Groq 429 (OpenAI-compatible shape)."""
    return litellm.RateLimitError(
        message="rate_limit_exceeded: TPM cap",
        llm_provider="groq",
        model="groq/llama-3.3-70b-versatile",
    )


# ---------------------------------------------------------------------------
# Per-provider auth-error builders
# ---------------------------------------------------------------------------


def anthropic_auth_error() -> litellm.AuthenticationError:
    return litellm.AuthenticationError(
        message="authentication_error: invalid api key",
        llm_provider="anthropic",
        model="claude-sonnet-4-6",
    )


def openai_auth_error() -> litellm.AuthenticationError:
    return litellm.AuthenticationError(
        message="invalid_api_key: incorrect API key provided",
        llm_provider="openai",
        model="gpt-4o",
    )


def gemini_auth_error() -> litellm.AuthenticationError:
    return litellm.AuthenticationError(
        message="PERMISSION_DENIED: API key not valid",
        llm_provider="gemini",
        model="gemini-2.0-flash",
    )


def groq_auth_error() -> litellm.AuthenticationError:
    return litellm.AuthenticationError(
        message="invalid_api_key: groq",
        llm_provider="groq",
        model="groq/llama-3.3-70b-versatile",
    )


# ---------------------------------------------------------------------------
# Per-provider successful-dispatch responses
# ---------------------------------------------------------------------------


def anthropic_response(content: str = "anthropic ok") -> StubResponse:
    return StubResponse.make(content=content, model="claude-sonnet-4-6")


def openai_response(content: str = "openai ok") -> StubResponse:
    return StubResponse.make(content=content, model="gpt-4o")


def gemini_response(content: str = "gemini ok") -> StubResponse:
    return StubResponse.make(content=content, model="gemini-2.0-flash")


def groq_response(content: str = "groq ok") -> StubResponse:
    return StubResponse.make(
        content=content,
        model="groq/llama-3.3-70b-versatile",
    )


def ollama_response(content: str = "ollama ok") -> StubResponse:
    return StubResponse.make(
        content=content,
        model="ollama_chat/llama3.2:1b",
    )
