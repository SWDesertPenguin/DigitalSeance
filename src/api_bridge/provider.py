"""LiteLLM provider bridge — dispatch, streaming, retry."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import litellm

from src.database.encryption import decrypt_value
from src.orchestrator.types import ProviderResponse
from src.repositories.errors import ProviderDispatchError

# Suppress LiteLLM's verbose logging
litellm.suppress_debug_info = True
# Disable aiohttp transport — its _make_common_async_call() silently
# drops the timeout parameter, causing Ollama requests to hang forever.
# httpx transport properly passes timeout to the HTTP client.
litellm.disable_aiohttp_transport = True


async def dispatch(
    *,
    model: str,
    messages: list[dict[str, str]],
    api_key_encrypted: str | None,
    encryption_key: str,
    api_base: str | None = None,
    timeout: int = 60,
    max_tokens: int | None = None,
) -> ProviderResponse:
    """Send payload to provider via LiteLLM."""
    api_key = _decrypt_key(api_key_encrypted, encryption_key)
    start = time.monotonic()
    try:
        response = await _call_litellm(
            model=model,
            messages=messages,
            api_key=api_key,
            api_base=api_base,
            timeout=timeout,
            max_tokens=max_tokens,
        )
        return _extract_response(response, model, start)
    finally:
        # Discard key immediately
        api_key = None  # noqa: F841


async def dispatch_with_retry(
    *,
    model: str,
    messages: list[dict[str, str]],
    api_key_encrypted: str | None,
    encryption_key: str,
    api_base: str | None = None,
    timeout: int = 60,
    max_tokens: int | None = None,
    max_retries: int = 3,
) -> ProviderResponse:
    """Dispatch with exponential backoff on rate limits."""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await dispatch(
                model=model,
                messages=messages,
                api_key_encrypted=api_key_encrypted,
                encryption_key=encryption_key,
                api_base=api_base,
                timeout=timeout,
                max_tokens=max_tokens,
            )
        except litellm.RateLimitError as e:
            last_error = e
            delay = _backoff_delay(attempt)
            await asyncio.sleep(delay)
        except (litellm.Timeout, TimeoutError) as e:
            last_error = e
            break  # Don't retry timeouts
        except Exception as e:
            last_error = e
            break  # Don't retry unknown errors
    raise ProviderDispatchError(
        f"Provider dispatch failed after {attempt + 1} attempts: {last_error}",
    )


def _decrypt_key(
    encrypted: str | None,
    encryption_key: str,
) -> str | None:
    """Decrypt API key if present."""
    if encrypted is None:
        return None
    return decrypt_value(encrypted, key=encryption_key)


async def _call_litellm(
    *,
    model: str,
    messages: list[dict[str, str]],
    api_key: str | None,
    api_base: str | None,
    timeout: int,
    max_tokens: int | None,
) -> Any:
    """Call litellm.acompletion with the given parameters."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "timeout": timeout,
    }
    if api_key and not model.startswith("ollama/"):
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    return await litellm.acompletion(**kwargs)


def _extract_response(
    response: Any,
    model: str,
    start_time: float,
) -> ProviderResponse:
    """Extract content, tokens, and cost from LiteLLM response."""
    choice = response.choices[0]
    content = choice.message.content or ""
    usage = response.usage
    latency = int((time.monotonic() - start_time) * 1000)
    return ProviderResponse(
        content=content,
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        cost_usd=_compute_cost(usage, model),
        model=model,
        latency_ms=latency,
    )


def _compute_cost(usage: Any, model: str) -> float:
    """Compute cost from token usage."""
    try:
        return litellm.completion_cost(
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
    except Exception:
        return 0.0  # Cost unknown for custom/local models


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: 1s, 2s, 4s..."""
    import random

    base = min(2**attempt, 60)
    return base + random.uniform(0, 1)  # noqa: S311
