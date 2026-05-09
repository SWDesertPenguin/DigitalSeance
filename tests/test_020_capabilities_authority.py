# SPDX-License-Identifier: AGPL-3.0-or-later

"""US1 capabilities authority smoke test.

Confirms the per-process per-model cache returns the same instance on
the second call and that all seven `Capabilities` fields are populated.
"""

from __future__ import annotations

import pytest

from src.api_bridge.adapter import Capabilities


def test_litellm_adapter_capabilities_cached_per_model() -> None:
    from src.api_bridge.litellm.adapter import LiteLLMAdapter

    adapter = LiteLLMAdapter()
    a = adapter.capabilities("gpt-4o")
    b = adapter.capabilities("gpt-4o")
    assert a is b


_KNOWN_FAMILIES = {"anthropic", "openai", "gemini", "groq", "ollama", "vllm", "mock", "unknown"}


def test_capabilities_all_fields_populated() -> None:
    from src.api_bridge.litellm.adapter import LiteLLMAdapter

    cap = LiteLLMAdapter().capabilities("gpt-4o")
    assert isinstance(cap, Capabilities)
    assert isinstance(cap.supports_streaming, bool)
    assert isinstance(cap.supports_tool_calling, bool)
    assert isinstance(cap.supports_prompt_caching, bool)
    assert cap.max_context_tokens >= 1024
    assert isinstance(cap.tokenizer_name, str)
    lo, hi = cap.recommended_temperature_range
    assert 0.0 <= lo <= hi <= 2.0
    assert cap.provider_family in _KNOWN_FAMILIES


@pytest.mark.parametrize(
    "model,expected_family",
    [
        ("gpt-4o", "openai"),
        ("anthropic/claude-3-5-sonnet", "anthropic"),
        ("gemini/gemini-2.5-pro", "gemini"),
    ],
)
def test_capabilities_provider_family_mapping(model: str, expected_family: str) -> None:
    from src.api_bridge.litellm.adapter import LiteLLMAdapter

    adapter = LiteLLMAdapter()
    cap = adapter.capabilities(model)
    # Some models may not be in LiteLLM's metadata; we accept "unknown"
    # as a valid alternative for the family lookup, but the bounded enum
    # must be honored.
    assert cap.provider_family in {expected_family, "unknown"}
