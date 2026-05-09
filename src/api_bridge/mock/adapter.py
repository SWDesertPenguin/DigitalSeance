"""Mock `ProviderAdapter` implementation per spec 020 US2.

Deterministic dispatch driven by JSON fixtures loaded from
`SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`. No network access; all
behavior is fixture-controlled. Useful for spec 015 circuit-breaker
tests, deferred-loading partition policy tests, and any code path that
needs predictable response content + token counts + streaming events.

The mock raises `MockFixtureMissingError` when no fixture matches an input
per FR-007 — never silently returns a default response.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from src.api_bridge.adapter import (
    CanonicalError,
    CanonicalErrorCategory,
    Capabilities,
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    StreamEvent,
    ValidationResult,
)
from src.api_bridge.mock import fixtures as _fixtures
from src.api_bridge.mock.errors import (
    MockFixtureMissingError,
    MockInjectedError,
)
from src.api_bridge.mock.streaming import default_stream

_DEFAULT_CAPABILITY_KEY = "default"
_DEFAULT_FALLBACK_CAPABILITIES = Capabilities(
    supports_streaming=True,
    supports_tool_calling=True,
    supports_prompt_caching=False,
    max_context_tokens=200_000,
    tokenizer_name="mock-tokenizer",
    recommended_temperature_range=(0.0, 1.0),
    provider_family="mock",
)


class MockAdapter(ProviderAdapter):
    """Fixture-driven `ProviderAdapter` for deterministic testing."""

    def __init__(self) -> None:
        path = os.environ.get("SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH")
        if not path:
            self._fixture_set = _fixtures.MockFixtureSet(
                responses=(),
                errors=(),
                capabilities={},
            )
        else:
            self._fixture_set = _fixtures.load(path)

    async def dispatch(self, request: ProviderRequest) -> ProviderResponse:
        return self._dispatch(request)

    async def dispatch_with_retry(self, request: ProviderRequest) -> ProviderResponse:
        return self._dispatch(request)

    async def stream(self, request: ProviderRequest) -> AsyncIterator[StreamEvent]:
        response_fixture = _fixtures.match_response(request.messages, self._fixture_set.responses)
        if response_fixture is not None:
            events = (
                response_fixture.stream_events
                if response_fixture.stream_events is not None
                else tuple(default_stream(response_fixture.response))
            )
            for event in events:
                yield event
            return
        error_fixture = _fixtures.match_error(request.messages, self._fixture_set.errors)
        if error_fixture is not None:
            raise MockInjectedError(
                category=error_fixture.canonical_category,
                provider_message=error_fixture.provider_message,
                retry_after_seconds=error_fixture.retry_after_seconds,
            )
        raise MockFixtureMissingError(
            canonical_hash=_fixtures.canonical_hash(request.messages),
            last_message_substring=_fixtures.last_message_text(request.messages)[:80],
        )

    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        # Deterministic count derived from the message text — useful for
        # tests that need a predictable token budget. The orchestrator's
        # spec 018 deferred-loading code can drive both branches by
        # writing different lengths.
        text = "".join(
            (msg.get("content") or "") if isinstance(msg.get("content"), str) else ""
            for msg in messages
        )
        return max(len(text) // 4, 1)

    async def validate_credentials(self, api_key: str, model: str) -> ValidationResult:
        # Mock always validates — tests that need to simulate auth
        # failure use the `errors` fixture entry with
        # `canonical_category="auth_error"` instead.
        return ValidationResult(ok=True)

    def capabilities(self, model: str) -> Capabilities:
        # The orchestrator passes a model name (which the mock ignores
        # for cap lookup). The fixture's `capabilities` dict is keyed by
        # capability-set name, defaulting to "default".
        cap_key = os.environ.get("SACP_MOCK_CAPABILITY_SET", _DEFAULT_CAPABILITY_KEY)
        cap = self._fixture_set.capabilities.get(cap_key)
        if cap is not None:
            return cap
        cap = self._fixture_set.capabilities.get(_DEFAULT_CAPABILITY_KEY)
        if cap is not None:
            return cap
        return _DEFAULT_FALLBACK_CAPABILITIES

    def normalize_error(self, exc: BaseException) -> CanonicalError:
        if isinstance(exc, MockInjectedError):
            return CanonicalError(
                category=exc.category,
                retry_after_seconds=exc.retry_after_seconds,
                original_exception=exc,
                provider_message=exc.provider_message,
            )
        return CanonicalError(
            category=CanonicalErrorCategory.UNKNOWN,
            original_exception=exc,
            provider_message=str(exc),
        )

    def _dispatch(self, request: ProviderRequest) -> ProviderResponse:
        response_fixture = _fixtures.match_response(request.messages, self._fixture_set.responses)
        if response_fixture is not None:
            return response_fixture.response
        error_fixture = _fixtures.match_error(request.messages, self._fixture_set.errors)
        if error_fixture is not None:
            raise MockInjectedError(
                category=error_fixture.canonical_category,
                provider_message=error_fixture.provider_message,
                retry_after_seconds=error_fixture.retry_after_seconds,
            )
        raise MockFixtureMissingError(
            canonical_hash=_fixtures.canonical_hash(request.messages),
            last_message_substring=_fixtures.last_message_text(request.messages)[:80],
        )
