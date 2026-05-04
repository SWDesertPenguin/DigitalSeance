"""Integration tests for LiteLLM provider dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import TEST_ENCRYPTION_KEY, _build_fake_response


def _encrypted_key() -> str:
    """Return a test API key encrypted with the shared test key."""
    from src.database.encryption import encrypt_value

    return encrypt_value("sk-test-key-123", key=TEST_ENCRYPTION_KEY)


def _base_kwargs() -> dict:
    """Common kwargs for dispatch calls."""
    return {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
        "api_key_encrypted": _encrypted_key(),
        "encryption_key": TEST_ENCRYPTION_KEY,
    }


async def test_dispatch_returns_provider_response(mock_litellm):
    """Successful dispatch returns a well-formed ProviderResponse."""
    from src.api_bridge.provider import dispatch

    result = await dispatch(**_base_kwargs())
    assert result.content == "Test AI response"
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.cost_usd == 0.001
    assert result.latency_ms >= 0
    mock_litellm.acompletion.assert_awaited_once()


async def test_dispatch_ollama_skips_api_key(mock_litellm):
    """Ollama models must not send api_key to litellm."""
    from src.api_bridge.provider import dispatch

    kwargs = _base_kwargs()
    kwargs["model"] = "ollama/llama3"
    await dispatch(**kwargs)
    call_kwargs = mock_litellm.acompletion.call_args.kwargs
    assert "api_key" not in call_kwargs


async def test_dispatch_passes_api_base(mock_litellm):
    """Custom api_base is forwarded to litellm.acompletion."""
    from src.api_bridge.provider import dispatch

    kwargs = _base_kwargs()
    kwargs["api_base"] = "http://localhost:11434"
    await dispatch(**kwargs)
    call_kwargs = mock_litellm.acompletion.call_args.kwargs
    assert call_kwargs["api_base"] == "http://localhost:11434"


async def test_dispatch_with_retry_succeeds(mock_litellm):
    """Happy path: retry wrapper succeeds on first attempt."""
    from src.api_bridge.provider import dispatch_with_retry

    result = await dispatch_with_retry(**_base_kwargs())
    assert result.content == "Test AI response"
    assert mock_litellm.acompletion.await_count == 1


async def test_retry_on_rate_limit(mock_litellm):
    """Rate limit errors trigger retry with backoff."""
    import litellm as _litellm

    from src.api_bridge.provider import dispatch_with_retry

    effects = [
        _litellm.RateLimitError("rate limited", "provider", "model", None),
        _litellm.RateLimitError("rate limited", "provider", "model", None),
        _build_fake_response(),
    ]
    mock_litellm.acompletion.side_effect = effects
    with patch("src.api_bridge.provider.asyncio.sleep", AsyncMock()):
        result = await dispatch_with_retry(**_base_kwargs())
    assert result.content == "Test AI response"
    assert mock_litellm.acompletion.await_count == 3


async def test_timeout_no_retry(mock_litellm):
    """Timeout errors must not be retried."""
    import litellm as _litellm

    from src.api_bridge.provider import dispatch_with_retry
    from src.repositories.errors import ProviderDispatchError

    mock_litellm.acompletion.side_effect = _litellm.Timeout(
        "timeout",
        "provider",
        "model",
    )
    with pytest.raises(ProviderDispatchError):
        await dispatch_with_retry(**_base_kwargs())
    assert mock_litellm.acompletion.await_count == 1


async def test_cost_fallback_to_zero(mock_litellm):
    """Unknown model cost falls back to 0.0."""
    from src.api_bridge.provider import dispatch

    mock_litellm.completion_cost.side_effect = Exception("unknown model")
    result = await dispatch(**_base_kwargs())
    assert result.cost_usd == 0.0


async def test_context_window_exceeded_surfaces_distinct_error(mock_litellm):
    """LiteLLM ContextWindowExceededError → ContextWindowOverflowError, not retried."""
    import litellm as _litellm

    from src.api_bridge.provider import dispatch_with_retry
    from src.repositories.errors import ContextWindowOverflowError

    mock_litellm.acompletion.side_effect = _litellm.ContextWindowExceededError(
        message="maximum context length is 16385 tokens",
        model="gpt-3.5-turbo",
        llm_provider="openai",
    )
    with pytest.raises(ContextWindowOverflowError):
        await dispatch_with_retry(**_base_kwargs())
    # Single attempt — must NOT retry. The next call would send the same
    # oversized payload and overshoot again.
    assert mock_litellm.acompletion.await_count == 1


async def test_context_window_overflow_is_provider_dispatch_error(mock_litellm):
    """ContextWindowOverflowError keeps the ProviderDispatchError ancestry."""
    import litellm as _litellm

    from src.api_bridge.provider import dispatch_with_retry
    from src.repositories.errors import ProviderDispatchError

    mock_litellm.acompletion.side_effect = _litellm.ContextWindowExceededError(
        message="maximum context length is 16385 tokens",
        model="gpt-3.5-turbo",
        llm_provider="openai",
    )
    # Existing handlers that catch ProviderDispatchError must still fire.
    with pytest.raises(ProviderDispatchError):
        await dispatch_with_retry(**_base_kwargs())
