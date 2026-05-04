"""LiteLLM provider bridge — dispatch, streaming, retry."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import litellm

from src.api_bridge.caching import CacheDirectives, apply_directives
from src.database.encryption import decrypt_value
from src.orchestrator.types import ProviderResponse
from src.repositories.errors import ContextWindowOverflowError, ProviderDispatchError

log = logging.getLogger(__name__)

# Suppress LiteLLM's verbose logging
litellm.suppress_debug_info = True
# Disable aiohttp transport — its _make_common_async_call() silently
# drops the timeout parameter, causing Ollama requests to hang forever.
# httpx transport properly passes timeout to the HTTP client.
litellm.disable_aiohttp_transport = True


async def dispatch(
    *,
    model: str,
    messages: list[dict[str, Any]],
    api_key_encrypted: str | None,
    encryption_key: str,
    api_base: str | None = None,
    timeout: int = 60,
    max_tokens: int | None = None,
    cache_directives: CacheDirectives | None = None,
) -> ProviderResponse:
    """Send payload to provider via LiteLLM."""
    api_key = _decrypt_key(api_key_encrypted, encryption_key)
    start = time.monotonic()
    log.info("Dispatching to %s (timeout=%ds)", model, timeout)
    heartbeat = asyncio.create_task(_log_heartbeat(model, timeout))
    try:
        response = await _call_litellm(
            model=model,
            messages=messages,
            api_key=api_key,
            api_base=api_base,
            timeout=timeout,
            max_tokens=max_tokens,
            cache_directives=cache_directives,
        )
        elapsed = int(time.monotonic() - start)
        log.info("%s responded in %ds", model, elapsed)
        return _extract_response(response, model, start)
    finally:
        heartbeat.cancel()
        api_key = None  # noqa: F841


async def dispatch_with_retry(
    *,
    model: str,
    messages: list[dict[str, Any]],
    api_key_encrypted: str | None,
    encryption_key: str,
    api_base: str | None = None,
    timeout: int = 60,
    max_tokens: int | None = None,
    max_retries: int = 3,
    cache_directives: CacheDirectives | None = None,
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
                cache_directives=cache_directives,
            )
        except litellm.ContextWindowExceededError as e:
            _raise_overflow(e)
        except litellm.RateLimitError as e:
            last_error = e
            await asyncio.sleep(_backoff_delay(attempt))
        except Exception as e:
            last_error = e
            break  # Timeouts + unknown errors aren't retried
    raise ProviderDispatchError(
        f"Provider dispatch failed after {attempt + 1} attempts: {last_error}",
    )


def _raise_overflow(e: BaseException) -> None:
    """Map LiteLLM's overshoot exception to ContextWindowOverflowError.

    Doesn't retry — the next attempt would send the same payload and
    overshoot again. The distinct error class lets RoutingLog record
    the overshoot rather than a generic provider_error.
    """
    raise ContextWindowOverflowError(
        f"Provider rejected request: context window exceeded ({e})",
    ) from e


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
    messages: list[dict[str, Any]],
    api_key: str | None,
    api_base: str | None,
    timeout: int,
    max_tokens: int | None,
    cache_directives: CacheDirectives | None = None,
) -> Any:
    """Call litellm.acompletion with the given parameters."""
    model = _normalize_ollama_model(model)
    messages, cache_kwargs = apply_directives(
        model=model,
        messages=messages,
        directives=cache_directives,
    )
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "timeout": timeout,
    }
    if api_key and not model.startswith(("ollama/", "ollama_chat/")):
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    kwargs.update(cache_kwargs)
    return await litellm.acompletion(**kwargs)


def _normalize_ollama_model(model: str) -> str:
    """Rewrite ollama/ to ollama_chat/ for the chat endpoint.

    LiteLLM's ollama/ prefix routes to /api/generate (text completion)
    which streams by default and times out with httpx. ollama_chat/
    routes to /api/chat which works correctly with chat messages.
    """
    if model.startswith("ollama/"):
        return model.replace("ollama/", "ollama_chat/", 1)
    return model


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
        cost_usd=_compute_cost(response, model),
        model=model,
        latency_ms=latency,
    )


def _compute_cost(response: Any, model: str) -> float:
    """Compute cost from the full LiteLLM response."""
    try:
        return litellm.completion_cost(completion_response=response)
    except Exception:
        log.debug("Cost lookup failed for %s, using 0", model)
        return 0.0  # Cost unknown for custom/local models


async def _log_heartbeat(model: str, timeout: int) -> None:
    """Log elapsed time every 15s while waiting for provider."""
    start = time.monotonic()
    while True:
        await asyncio.sleep(15)
        elapsed = int(time.monotonic() - start)
        remaining = timeout - elapsed
        log.info(
            "Waiting for %s… %ds elapsed, %ds remaining",
            model,
            elapsed,
            remaining,
        )


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: 1s, 2s, 4s..."""
    import random

    base = min(2**attempt, 60)
    return base + random.uniform(0, 1)  # noqa: S311
