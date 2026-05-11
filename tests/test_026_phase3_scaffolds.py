# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 Phase 3 scaffold tests (T045 of US5 + T047 of US6).

Provence (Layer 5) and Layer 6 are stubs in v1. Provence raises
NotImplementedError unconditionally pending a retrieval spec. Layer 6
exposes a `supports(provider)` discriminator: True for open-weight
legs (Ollama, vLLM); False for closed-API legs (Anthropic, OpenAI,
Google) — closed-API legs structurally skip Layer 6 per FR-022 + SC-011.
"""

from __future__ import annotations

import pytest

from src.compression.layer6 import NoOpLayer6Adapter
from src.compression.provence import NoOpProvenceAdapter
from src.compression.trust_tier import TierOneRefusalError

# ---------------------------------------------------------------------------
# NoOpProvenceAdapter (Layer 5)
# ---------------------------------------------------------------------------


def test_provence_metadata() -> None:
    assert NoOpProvenceAdapter.COMPRESSOR_ID == "provence"
    assert NoOpProvenceAdapter.COMPRESSOR_VERSION == "0-stub"


def test_provence_raises_until_retrieval_spec() -> None:
    adapter = NoOpProvenceAdapter()
    with pytest.raises(NotImplementedError, match="retrieval surface"):
        adapter.compress("x", target_budget=1, trust_tier="participant_supplied")


def test_provence_refuses_tier_one() -> None:
    adapter = NoOpProvenceAdapter()
    with pytest.raises(TierOneRefusalError):
        adapter.compress("x", target_budget=1, trust_tier="system")


# ---------------------------------------------------------------------------
# NoOpLayer6Adapter (Layer 6)
# ---------------------------------------------------------------------------


def test_layer6_metadata() -> None:
    assert NoOpLayer6Adapter.COMPRESSOR_ID == "layer6"
    assert NoOpLayer6Adapter.COMPRESSOR_VERSION == "0-stub"


@pytest.mark.parametrize("provider", ["ollama", "vllm"])
def test_layer6_supports_open_weight_providers(provider: str) -> None:
    assert NoOpLayer6Adapter.supports(provider) is True


@pytest.mark.parametrize("provider", ["anthropic", "openai", "google", "azure", "deepseek"])
def test_layer6_skips_closed_api_providers(provider: str) -> None:
    assert NoOpLayer6Adapter.supports(provider) is False


def test_layer6_raises_until_local_model_spec() -> None:
    adapter = NoOpLayer6Adapter()
    with pytest.raises(NotImplementedError, match="local-model support"):
        adapter.compress("x", target_budget=1, trust_tier="participant_supplied")


def test_layer6_refuses_tier_one() -> None:
    adapter = NoOpLayer6Adapter()
    with pytest.raises(TierOneRefusalError):
        adapter.compress("x", target_budget=1, trust_tier="system")
