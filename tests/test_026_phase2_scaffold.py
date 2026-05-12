# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 Phase 2 scaffold tests (T039-T040 of US4).

Both LLMLingua2mBERTCompressor and SelectiveContextCompressor are
scaffold-only in Phase 1. They raise NotImplementedError until Phase 2
ships the real bodies; the env-var gate flips the message.
"""

from __future__ import annotations

import pytest

from src.compression.llmlingua2_mbert import LLMLingua2mBERTCompressor
from src.compression.selective_context import SelectiveContextCompressor


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SACP_COMPRESSION_PHASE2_ENABLED", raising=False)


# ---------------------------------------------------------------------------
# LLMLingua2mBERTCompressor
# ---------------------------------------------------------------------------


def test_llmlingua_phase2_off_raises_on_dispatch() -> None:
    compressor = LLMLingua2mBERTCompressor()
    with pytest.raises(NotImplementedError, match="Phase 2 not enabled"):
        compressor.compress("x", target_budget=1, trust_tier="participant_supplied")


def test_llmlingua_phase2_on_still_scaffolded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "true")
    compressor = LLMLingua2mBERTCompressor()
    with pytest.raises(NotImplementedError, match="Phase 2 task list"):
        compressor.compress("x", target_budget=1, trust_tier="participant_supplied")


def test_llmlingua_refuses_tier_one() -> None:
    """FR-014: non-NoOp compressors refuse tier-1 input regardless of phase gate."""
    from src.compression.trust_tier import TierOneRefusalError

    compressor = LLMLingua2mBERTCompressor()
    with pytest.raises(TierOneRefusalError):
        compressor.compress("x", target_budget=1, trust_tier="system")


def test_llmlingua_metadata() -> None:
    assert LLMLingua2mBERTCompressor.COMPRESSOR_ID == "llmlingua2_mbert"
    assert LLMLingua2mBERTCompressor.COMPRESSOR_VERSION == "0-scaffold"


# ---------------------------------------------------------------------------
# SelectiveContextCompressor
# ---------------------------------------------------------------------------


def test_selective_context_phase2_off_raises_on_dispatch() -> None:
    compressor = SelectiveContextCompressor()
    with pytest.raises(NotImplementedError, match="Phase 2 not enabled"):
        compressor.compress("x", target_budget=1, trust_tier="participant_supplied")


def test_selective_context_phase2_on_still_scaffolded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "true")
    compressor = SelectiveContextCompressor()
    with pytest.raises(NotImplementedError, match="Phase 2 task list"):
        compressor.compress("x", target_budget=1, trust_tier="participant_supplied")


def test_selective_context_refuses_tier_one() -> None:
    from src.compression.trust_tier import TierOneRefusalError

    compressor = SelectiveContextCompressor()
    with pytest.raises(TierOneRefusalError):
        compressor.compress("x", target_budget=1, trust_tier="system")


def test_selective_context_metadata() -> None:
    assert SelectiveContextCompressor.COMPRESSOR_ID == "selective_context"
    assert SelectiveContextCompressor.COMPRESSOR_VERSION == "0-scaffold"
