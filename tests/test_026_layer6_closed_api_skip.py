# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 T048 + T050 — SC-011 Layer 6 closed-API skip.

Layer 6 (Activation Beacon / ICAE / KV-cache) applies ONLY to legs
running open-weight models the orchestrator controls (Ollama, vLLM).
On closed-API legs (Anthropic, OpenAI, Gemini) the dispatch path MUST
fall back to NoOp without emitting ``compression_pipeline_error`` —
the skip is by design, not a failure.

The discriminator lives on the ``NoOpLayer6Adapter`` (``supports``
classmethod); the service-layer skip lives in
``CompressorService._layer6_closed_api_skip``. Both surfaces are
covered here.
"""

from __future__ import annotations

import pytest

from src.compression import _telemetry_sink
from src.compression.layer6 import NoOpLayer6Adapter
from src.compression.noop import NoOpCompressor
from src.compression.service import CompressorService


@pytest.fixture(autouse=True)
def _clear_sink() -> None:
    _telemetry_sink.clear()


def _fresh_service() -> CompressorService:
    svc = CompressorService()
    svc.register(NoOpCompressor.COMPRESSOR_ID, NoOpCompressor)
    svc.register(NoOpLayer6Adapter.COMPRESSOR_ID, NoOpLayer6Adapter)
    return svc


def test_supports_returns_false_for_closed_api_providers() -> None:
    """The static discriminator rejects every closed-API provider."""
    for provider in ("anthropic", "openai", "google", "gemini", "groq"):
        assert NoOpLayer6Adapter.supports(provider) is False


def test_supports_returns_true_for_open_weight_providers() -> None:
    """Ollama and vLLM expose activation-tensor access; Layer 6 applies."""
    assert NoOpLayer6Adapter.supports("ollama") is True
    assert NoOpLayer6Adapter.supports("vllm") is True


def test_layer6_on_closed_api_falls_back_to_noop_without_error() -> None:
    """SC-011: closed-API leg + layer6 selected -> NoOp telemetry, no error."""
    svc = _fresh_service()
    segment = svc.compress(
        "payload",
        target_budget=100,
        trust_tier="participant_supplied",
        compressor_id="layer6",
        session_id="s",
        participant_id="p",
        turn_id="t",
        provider="anthropic",
    )
    assert segment.compressor_id == "noop"
    assert _telemetry_sink.records()[0].compressor_id == "noop"
    assert _telemetry_sink.records()[0].succeeded is True


def test_layer6_on_openai_leg_falls_back_to_noop() -> None:
    """OpenAI is closed-API; the skip applies the same way."""
    svc = _fresh_service()
    segment = svc.compress(
        "payload",
        target_budget=100,
        trust_tier="participant_supplied",
        compressor_id="layer6",
        session_id="s",
        participant_id="p",
        turn_id="t",
        provider="openai",
    )
    assert segment.compressor_id == "noop"


def test_layer6_on_ollama_leg_does_not_skip() -> None:
    """Open-weight legs DO route through Layer 6 — and raise NotImplemented (stub)."""
    svc = _fresh_service()
    with pytest.raises(Exception, match="Layer 6"):
        svc.compress(
            "payload",
            target_budget=100,
            trust_tier="participant_supplied",
            compressor_id="layer6",
            session_id="s",
            participant_id="p",
            turn_id="t",
            provider="ollama",
        )


def test_layer6_without_provider_arg_preserves_pre_t050_behaviour() -> None:
    """Legacy callers that omit ``provider`` keep the old (no-skip) path."""
    svc = _fresh_service()
    # No ``provider`` -> Layer 6 stub raises NotImplementedError; the
    # service wraps that in CompressionPipelineError per FR-020.
    with pytest.raises(Exception, match="layer6"):
        svc.compress(
            "payload",
            target_budget=100,
            trust_tier="participant_supplied",
            compressor_id="layer6",
            session_id="s",
            participant_id="p",
            turn_id="t",
        )
