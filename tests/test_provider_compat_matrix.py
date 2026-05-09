# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider compatibility matrix testability suite (Phase F).

Cross-cutting audit (no per-spec FR markers). Cross-ref
``docs/provider-compatibility-matrix.md`` for the per-provider behaviour
table this suite exercises.

Covers audit-plan items:

* Per-provider rate-limit normalisation: each provider's 429 surfaces
  as ``litellm.RateLimitError`` and triggers the dispatch-with-retry
  retry path.
* Per-provider auth-error normalisation: each provider's 401 surfaces
  as ``litellm.AuthenticationError`` and propagates as
  ``ProviderDispatchError`` (no retry — auth failures are operator-fix).
* Cost-calculation fallback for null-cost providers: Ollama (and any
  unknown model) returns ``cost = 0.0`` rather than raising.
* max_tokens passthrough: when supplied, the kwarg is forwarded; when
  null, the kwarg is omitted entirely.
* Ollama prefix normalisation: ``ollama/`` -> ``ollama_chat/`` rewrite
  is applied at dispatch time.
"""

# ruff: noqa: I001
# Import order: src.auth must be primed before src.api_bridge.litellm.dispatch's
# dispatch path is exercised through src.repositories.

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import src.auth  # noqa: F401  -- prime auth package
import litellm

from src.api_bridge.litellm.dispatch import (
    _compute_cost,
    _normalize_ollama_model,
    dispatch,
    dispatch_with_retry,
)
from src.repositories.errors import ProviderDispatchError
from tests.conftest import TEST_ENCRYPTION_KEY
from tests.fixtures import provider_stubs


def _encrypted_key() -> str:
    """Return a test API key encrypted with the shared test key."""
    from src.database.encryption import encrypt_value

    return encrypt_value("sk-test-key-123", key=TEST_ENCRYPTION_KEY)


def _base_kwargs(model: str = "gpt-4o") -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "api_key_encrypted": _encrypted_key(),
        "encryption_key": TEST_ENCRYPTION_KEY,
    }


# ---------------------------------------------------------------------------
# Per-provider rate-limit normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,model,builder",
    [
        ("anthropic", "claude-sonnet-4-6", provider_stubs.anthropic_rate_limit),
        ("openai", "gpt-4o", provider_stubs.openai_rate_limit),
        ("gemini", "gemini/gemini-2.0-flash", provider_stubs.gemini_rate_limit),
        ("groq", "groq/llama-3.3-70b-versatile", provider_stubs.groq_rate_limit),
    ],
    ids=["anthropic", "openai", "gemini", "groq"],
)
async def test_per_provider_rate_limit_triggers_retry(
    label: str,
    model: str,
    builder,
) -> None:
    """RateLimitError from any provider is caught and retried by dispatch_with_retry."""
    err = builder()
    with patch("src.api_bridge.litellm.dispatch.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(side_effect=err)
        mock_litellm.RateLimitError = litellm.RateLimitError
        mock_litellm.Timeout = litellm.Timeout
        mock_litellm.ContextWindowExceededError = litellm.ContextWindowExceededError
        mock_litellm.suppress_debug_info = True
        with (
            patch("src.api_bridge.litellm.dispatch.asyncio.sleep", new=AsyncMock()),
            pytest.raises(ProviderDispatchError),
        ):
            await dispatch_with_retry(**_base_kwargs(model=model), max_retries=2)
        # All max_retries attempts must have been made (rate-limit path retries).
        assert mock_litellm.acompletion.await_count == 2


# ---------------------------------------------------------------------------
# Per-provider auth-error normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,model,builder",
    [
        ("anthropic", "claude-sonnet-4-6", provider_stubs.anthropic_auth_error),
        ("openai", "gpt-4o", provider_stubs.openai_auth_error),
        ("gemini", "gemini/gemini-2.0-flash", provider_stubs.gemini_auth_error),
        ("groq", "groq/llama-3.3-70b-versatile", provider_stubs.groq_auth_error),
    ],
    ids=["anthropic", "openai", "gemini", "groq"],
)
async def test_per_provider_auth_error_does_not_retry(
    label: str,
    model: str,
    builder,
) -> None:
    """AuthenticationError surfaces as ProviderDispatchError on the first attempt."""
    err = builder()
    with patch("src.api_bridge.litellm.dispatch.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(side_effect=err)
        mock_litellm.RateLimitError = litellm.RateLimitError
        mock_litellm.Timeout = litellm.Timeout
        mock_litellm.ContextWindowExceededError = litellm.ContextWindowExceededError
        mock_litellm.suppress_debug_info = True
        with pytest.raises(ProviderDispatchError):
            await dispatch_with_retry(**_base_kwargs(model=model), max_retries=3)
        # Auth errors break out immediately — only one attempt.
        assert mock_litellm.acompletion.await_count == 1


# ---------------------------------------------------------------------------
# Cost-calculation fallback (null-cost providers like Ollama)
# ---------------------------------------------------------------------------


def test_compute_cost_returns_zero_when_lookup_raises() -> None:
    """Models LiteLLM doesn't price (Ollama, custom) get cost = 0.0, not exception."""
    response = provider_stubs.ollama_response()
    with patch("src.api_bridge.litellm.dispatch.litellm") as mock_litellm:
        mock_litellm.completion_cost.side_effect = Exception("model not in registry")
        cost = _compute_cost(response, "ollama_chat/llama3.2:1b")
    assert cost == 0.0


def test_compute_cost_uses_litellm_when_lookup_succeeds() -> None:
    """Priced models return whatever LiteLLM's registry reports."""
    response = provider_stubs.openai_response()
    with patch("src.api_bridge.litellm.dispatch.litellm") as mock_litellm:
        mock_litellm.completion_cost.return_value = 0.0042
        cost = _compute_cost(response, "gpt-4o")
    assert cost == 0.0042


# ---------------------------------------------------------------------------
# max_tokens passthrough
# ---------------------------------------------------------------------------


async def test_max_tokens_omitted_when_none() -> None:
    """When max_tokens kwarg is None, the field is absent in the LiteLLM call."""
    with patch("src.api_bridge.litellm.dispatch.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=provider_stubs.openai_response())
        mock_litellm.completion_cost.return_value = 0.001
        mock_litellm.suppress_debug_info = True
        await dispatch(**_base_kwargs(), max_tokens=None)
        call_kwargs = mock_litellm.acompletion.await_args.kwargs
        assert "max_tokens" not in call_kwargs


async def test_max_tokens_forwarded_when_set() -> None:
    """When max_tokens kwarg is supplied, the value reaches the LiteLLM call."""
    with patch("src.api_bridge.litellm.dispatch.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=provider_stubs.openai_response())
        mock_litellm.completion_cost.return_value = 0.001
        mock_litellm.suppress_debug_info = True
        await dispatch(**_base_kwargs(), max_tokens=512)
        call_kwargs = mock_litellm.acompletion.await_args.kwargs
        assert call_kwargs.get("max_tokens") == 512


# ---------------------------------------------------------------------------
# Ollama prefix normalisation
# ---------------------------------------------------------------------------


def test_ollama_prefix_rewritten_to_chat() -> None:
    """`ollama/` rewrites to `ollama_chat/` to hit /api/chat instead of /api/generate."""
    assert _normalize_ollama_model("ollama/llama3.2:1b") == "ollama_chat/llama3.2:1b"


def test_ollama_chat_prefix_passthrough() -> None:
    """`ollama_chat/` is already correct; no further rewrite."""
    assert _normalize_ollama_model("ollama_chat/llama3.2:1b") == "ollama_chat/llama3.2:1b"


def test_non_ollama_model_passthrough() -> None:
    """Other prefixes pass through untouched."""
    for model in (
        "gpt-4o",
        "claude-sonnet-4-6",
        "gemini/gemini-2.0-flash",
        "groq/llama-3.3-70b-versatile",
    ):
        assert _normalize_ollama_model(model) == model


# ---------------------------------------------------------------------------
# api_key suppression for Ollama
# ---------------------------------------------------------------------------


async def test_ollama_request_omits_api_key() -> None:
    """Ollama dispatches MUST NOT pass an api_key kwarg (local server, no auth)."""
    with patch("src.api_bridge.litellm.dispatch.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=provider_stubs.ollama_response())
        mock_litellm.completion_cost.return_value = 0.0
        mock_litellm.suppress_debug_info = True
        # Pass an encrypted "key" — provider.py decrypts it but should not forward
        # to LiteLLM for ollama_ models.
        await dispatch(**_base_kwargs(model="ollama_chat/llama3.2:1b"))
        call_kwargs = mock_litellm.acompletion.await_args.kwargs
        assert "api_key" not in call_kwargs


async def test_non_ollama_request_includes_api_key_when_present() -> None:
    """Non-Ollama dispatches DO pass api_key when supplied."""
    with patch("src.api_bridge.litellm.dispatch.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=provider_stubs.openai_response())
        mock_litellm.completion_cost.return_value = 0.001
        mock_litellm.suppress_debug_info = True
        await dispatch(**_base_kwargs(model="gpt-4o"))
        call_kwargs = mock_litellm.acompletion.await_args.kwargs
        assert call_kwargs.get("api_key") == "sk-test-key-123"
