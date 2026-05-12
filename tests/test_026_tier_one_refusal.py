# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 T053 — FR-014 tier-1 refusal end-to-end.

Tier-1 (``'system'``) content MUST NOT reach a non-NoOp compressor.
The compressor body calls ``refuse_tier_one(trust_tier)`` at entry;
the CompressorService catches the resulting ``TierOneRefusalError``,
wraps it in ``CompressionPipelineError``, and records the
``compression_pipeline_error`` telemetry row. The dispatch path then
falls through to un-compressed payload per FR-020.

NoOp is exempt per the spec — it produces no compression artefact, so
the protective rationale does not apply.
"""

from __future__ import annotations

import pytest

from src.compression import _telemetry_sink
from src.compression.noop import NoOpCompressor
from src.compression.segments import CompressedSegment
from src.compression.service import CompressionPipelineError, CompressorService
from src.compression.trust_tier import TierOneRefusalError, refuse_tier_one


class _TierAwareCompressor:
    """A non-NoOp compressor stand-in that calls refuse_tier_one at entry."""

    COMPRESSOR_ID: str = "tier_aware"
    COMPRESSOR_VERSION: str = "test"

    def compress(self, payload: str, target_budget: int, trust_tier: str) -> CompressedSegment:
        refuse_tier_one(trust_tier)
        return CompressedSegment(
            output_text=payload,
            output_tokens=len(payload),
            trust_tier=trust_tier,
            boundary_marker="<wrap>",
            compressor_id=self.COMPRESSOR_ID,
            compressor_version=self.COMPRESSOR_VERSION,
        )


@pytest.fixture(autouse=True)
def _clear_sink() -> None:
    _telemetry_sink.clear()


def test_refuse_tier_one_raises_for_system_tier() -> None:
    """The trust-tier helper raises TierOneRefusalError on 'system'."""
    with pytest.raises(TierOneRefusalError, match="tier-1"):
        refuse_tier_one("system")


def test_refuse_tier_one_passes_through_lower_tiers() -> None:
    """Tier-2 and tier-3 inputs pass without error."""
    refuse_tier_one("facilitator")
    refuse_tier_one("participant_supplied")


def test_compressor_service_wraps_tier_one_refusal_as_pipeline_error() -> None:
    """Service-layer catches TierOneRefusalError and surfaces it via FR-020."""
    svc = CompressorService()
    svc.register("tier_aware", _TierAwareCompressor)
    with pytest.raises(CompressionPipelineError, match="tier_aware"):
        svc.compress(
            "system prompt body",
            target_budget=100,
            trust_tier="system",
            compressor_id="tier_aware",
            session_id="s",
            participant_id="p",
            turn_id="t",
        )
    records = _telemetry_sink.records()
    assert len(records) == 1
    assert records[0].succeeded is False
    assert records[0].error_class == "TierOneRefusalError"


def test_noop_is_exempt_from_tier_one_refusal() -> None:
    """NoOpCompressor passes tier-1 through verbatim; no exception raised."""
    svc = CompressorService()
    svc.register("noop", NoOpCompressor)
    segment = svc.compress(
        "system prompt body",
        target_budget=100,
        trust_tier="system",
        compressor_id="noop",
        session_id="s",
        participant_id="p",
        turn_id="t",
    )
    assert segment.output_text == "system prompt body"
    assert segment.trust_tier == "system"
