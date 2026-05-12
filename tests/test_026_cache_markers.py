# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 T023 + T024 + T025 — cache_hit / cache_miss routing_log markers.

Covers FR-003 + SC-002. The bridge layer surfaces a provider-side cache
marker on every dispatch where the adapter populates
``ProviderResponse.cached_prefix_tokens`` from the LiteLLM usage payload
(Anthropic ``cache_read_input_tokens``, OpenAI
``prompt_tokens_details.cached_tokens``). The loop emits a
``routing_log.reason='cache_hit'`` (positive token count) or
``'cache_miss'`` (zero) row alongside the standard turn row; when the
adapter reports None (no provider-side marker) no extra row is emitted.

Tests target the extractor (``extract_cached_prefix_tokens``) and the
loop helper (``_emit_cache_marker``) independently — both are pure
functions with mock log repositories, so no live DB is needed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api_bridge.adapter import ProviderResponse
from src.api_bridge.cache_markers import emit_cache_marker
from src.api_bridge.caching import extract_cached_prefix_tokens


def _response_with(cached_prefix_tokens: int | None) -> ProviderResponse:
    return ProviderResponse(
        content="hi",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.0,
        model="claude-haiku",
        latency_ms=1,
        cached_prefix_tokens=cached_prefix_tokens,
    )


def test_extract_cached_prefix_tokens_anthropic_hit() -> None:
    """Anthropic's ``cache_read_input_tokens`` exposes the cache-hit count."""
    usage = SimpleNamespace(cache_read_input_tokens=128, prompt_tokens_details=None)
    assert extract_cached_prefix_tokens(usage) == 128


def test_extract_cached_prefix_tokens_openai_hit() -> None:
    """OpenAI's ``prompt_tokens_details.cached_tokens`` exposes the count."""
    details = SimpleNamespace(cached_tokens=256)
    usage = SimpleNamespace(prompt_tokens_details=details, cache_read_input_tokens=None)
    assert extract_cached_prefix_tokens(usage) == 256


def test_extract_cached_prefix_tokens_openai_miss() -> None:
    """A zero ``cached_tokens`` value is a cache miss, not absence of signal."""
    details = SimpleNamespace(cached_tokens=0)
    usage = SimpleNamespace(prompt_tokens_details=details, cache_read_input_tokens=None)
    assert extract_cached_prefix_tokens(usage) == 0


def test_extract_cached_prefix_tokens_dict_shape() -> None:
    """LiteLLM dict-shaped usage payloads work via the mapping fallback."""
    usage = {"prompt_tokens_details": {"cached_tokens": 64}}
    assert extract_cached_prefix_tokens(usage) == 64


def test_extract_cached_prefix_tokens_returns_none_when_unset() -> None:
    """Absent marker fields = None (provider does not surface cache info)."""
    assert extract_cached_prefix_tokens(None) is None
    assert extract_cached_prefix_tokens(SimpleNamespace()) is None
    assert extract_cached_prefix_tokens({}) is None


@pytest.mark.asyncio
async def test_cache_marker_emits_cache_hit_on_positive_tokens() -> None:
    """Acceptance scenario 4: provider cache-hit -> routing_log row with reason cache_hit."""
    log_repo = SimpleNamespace(log_routing=AsyncMock())
    speaker = SimpleNamespace(id="pp-1")
    await emit_cache_marker(log_repo, "sess-1", 7, speaker, _response_with(128))
    log_repo.log_routing.assert_awaited_once_with(
        session_id="sess-1",
        turn_number=7,
        intended="pp-1",
        actual="pp-1",
        action="cache_event",
        complexity="n/a",
        domain_match=False,
        reason="cache_hit",
    )


@pytest.mark.asyncio
async def test_cache_marker_emits_cache_miss_on_zero_tokens() -> None:
    """Acceptance scenario 5: provider cache-miss -> routing_log row with reason cache_miss."""
    log_repo = SimpleNamespace(log_routing=AsyncMock())
    speaker = SimpleNamespace(id="pp-1")
    await emit_cache_marker(log_repo, "sess-1", 1, speaker, _response_with(0))
    log_repo.log_routing.assert_awaited_once()
    kwargs = log_repo.log_routing.await_args.kwargs
    assert kwargs["reason"] == "cache_miss"


@pytest.mark.asyncio
async def test_cache_marker_silent_when_provider_has_no_marker() -> None:
    """No marker field on the response -> no extra routing_log row."""
    log_repo = SimpleNamespace(log_routing=AsyncMock())
    speaker = SimpleNamespace(id="pp-1")
    await emit_cache_marker(log_repo, "sess-1", 1, speaker, _response_with(None))
    log_repo.log_routing.assert_not_called()


@pytest.mark.asyncio
async def test_cache_marker_uses_speaker_id_for_intended_and_actual() -> None:
    """The cache event attributes to the dispatched participant, not the session."""
    log_repo = SimpleNamespace(log_routing=AsyncMock())
    speaker = SimpleNamespace(id="participant-abc")
    await emit_cache_marker(log_repo, "sess-z", 9, speaker, _response_with(42))
    kwargs = log_repo.log_routing.await_args.kwargs
    assert kwargs["intended"] == "participant-abc"
    assert kwargs["actual"] == "participant-abc"


def test_provider_response_cached_prefix_tokens_default_none() -> None:
    """Backward compatibility: pre-026 callers omit the field; default is None."""
    response = ProviderResponse(
        content="x",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
        model="m",
        latency_ms=0,
    )
    assert response.cached_prefix_tokens is None
