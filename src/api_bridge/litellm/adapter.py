# SPDX-License-Identifier: AGPL-3.0-or-later

"""LiteLLM-backed `ProviderAdapter` implementation per spec 020 US1.

Thin wrapper that delegates to the helper modules in this package. The
class is registered with `AdapterRegistry` under the name `"litellm"`
in `src.api_bridge.litellm.__init__` at module-import time per
research.md §4.

The adapter preserves pre-feature byte-identical behavior per FR-014 /
SC-001 — every method's behavior matches the pre-spec-020 dispatch path
exactly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import litellm

from src.api_bridge.adapter import (
    CanonicalError,
    Capabilities,
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    StreamEvent,
    ValidationResult,
)
from src.api_bridge.litellm import dispatch as _dispatch_module
from src.api_bridge.litellm.capabilities import compute_capabilities
from src.api_bridge.litellm.errors import normalize_litellm_error
from src.api_bridge.litellm.streaming import normalize_litellm_stream
from src.api_bridge.litellm.tokens import count_tokens as _count_tokens


class LiteLLMAdapter(ProviderAdapter):
    """LiteLLM-backed adapter; the v1 production-path implementation."""

    def __init__(self) -> None:
        self._cap_cache: dict[str, Capabilities] = {}

    async def dispatch(self, request: ProviderRequest) -> ProviderResponse:
        return await _dispatch_module.dispatch(
            model=request.model,
            messages=request.messages,
            api_key_encrypted=request.api_key_encrypted,
            encryption_key=request.encryption_key,
            api_base=request.api_base,
            timeout=request.timeout,
            max_tokens=request.max_tokens,
            cache_directives=request.cache_directives,
        )

    async def dispatch_with_retry(self, request: ProviderRequest) -> ProviderResponse:
        return await _dispatch_module.dispatch_with_retry(
            model=request.model,
            messages=request.messages,
            api_key_encrypted=request.api_key_encrypted,
            encryption_key=request.encryption_key,
            api_base=request.api_base,
            timeout=request.timeout,
            max_tokens=request.max_tokens,
            cache_directives=request.cache_directives,
        )

    async def stream(self, request: ProviderRequest) -> AsyncIterator[StreamEvent]:
        provider_iter = await _build_stream(request)
        async for event in normalize_litellm_stream(provider_iter):
            yield event

    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        return _count_tokens(messages, model)

    async def validate_credentials(self, api_key: str, model: str) -> ValidationResult:
        # v1: lightweight check — look up the provider for the model and
        # confirm LiteLLM recognizes the routing. Real network probing is
        # out of scope for v1 (would require model-specific endpoints).
        try:
            litellm.get_llm_provider(model)
        except Exception as exc:
            return ValidationResult(ok=False, detail=str(exc))
        return ValidationResult(ok=bool(api_key), detail=None if api_key else "missing api key")

    def capabilities(self, model: str) -> Capabilities:
        cached = self._cap_cache.get(model)
        if cached is not None:
            return cached
        result = compute_capabilities(model)
        self._cap_cache[model] = result
        return result

    def normalize_error(self, exc: BaseException) -> CanonicalError:
        return normalize_litellm_error(exc)


async def _build_stream(request: ProviderRequest) -> AsyncIterator[Any]:
    """Build the LiteLLM streaming iterator (forward-looking; no pre-feature consumer)."""
    from src.api_bridge.caching import apply_directives  # local to avoid cycle
    from src.database.encryption import decrypt_value

    api_key = (
        decrypt_value(request.api_key_encrypted, key=request.encryption_key)
        if request.api_key_encrypted
        else None
    )
    messages, cache_kwargs = apply_directives(
        model=request.model, messages=request.messages, directives=request.cache_directives
    )
    kwargs: dict[str, Any] = {
        "model": request.model,
        "messages": messages,
        "timeout": request.timeout,
        "stream": True,
    }
    if api_key and not request.model.startswith(("ollama/", "ollama_chat/")):
        kwargs["api_key"] = api_key
    if request.api_base:
        kwargs["api_base"] = request.api_base
    if request.max_tokens:
        kwargs["max_tokens"] = request.max_tokens
    kwargs.update(cache_kwargs)
    return await litellm.acompletion(**kwargs)
