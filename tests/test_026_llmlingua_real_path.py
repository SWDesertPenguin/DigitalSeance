# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 — LLMLingua-2 mBERT real-path body (Phase 2 layer 4).

The Phase 2 master switch + the optional ``llmlingua`` dep gate the
real body. These tests stub the ``llmlingua.PromptCompressor`` import
so the per-test environment doesn't need the ~2 GB Phase 2 extra
installed. Real-integration verification rides the per-stack Phase 2
quickstart smoke test (out-of-scope for the unit suite).
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from src.compression import llmlingua2_mbert
from src.compression.llmlingua2_mbert import LLMLingua2mBERTCompressor
from src.compression.markers import wrap as wrap_boundary_marker


class _StubPromptCompressor:
    """Mirrors the llmlingua PromptCompressor.compress_prompt(...) contract."""

    def __init__(self, *_: Any, **__: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    def compress_prompt(
        self,
        context: list[str],
        target_token: int,
        use_sentence_level_filter: bool,
        use_token_level_filter: bool,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "target_token": target_token,
                "use_sentence_level_filter": use_sentence_level_filter,
                "use_token_level_filter": use_token_level_filter,
            }
        )
        return {
            "compressed_prompt": "alpha gamma",
            "compressed_tokens": 2,
        }


@pytest.fixture
def _install_llmlingua_stub(monkeypatch: pytest.MonkeyPatch):
    """Insert a fake ``llmlingua`` module exposing the stub PromptCompressor."""
    fake = types.ModuleType("llmlingua")
    fake.PromptCompressor = _StubPromptCompressor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llmlingua", fake)
    llmlingua2_mbert._reset_model_for_tests()
    yield fake
    llmlingua2_mbert._reset_model_for_tests()


def test_real_path_emits_compressed_segment_with_boundary_marker(
    monkeypatch: pytest.MonkeyPatch, _install_llmlingua_stub: Any
) -> None:
    """Phase 2 ON + dep present -> compress_prompt drives a wrapped segment."""
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "true")
    compressor = LLMLingua2mBERTCompressor()
    segment = compressor.compress(
        "alpha beta gamma",
        target_budget=4,
        trust_tier="participant_supplied",
    )
    assert "alpha gamma" in segment.output_text
    assert segment.output_text.startswith("<compressed")
    assert segment.output_text.endswith("</compressed>")
    assert segment.compressor_id == "llmlingua2_mbert"
    assert segment.compressor_version == "1-llmlingua-real"
    assert segment.trust_tier == "participant_supplied"
    expected_marker = wrap_boundary_marker(
        "",
        source_tier="participant_supplied",
        compressor_id="llmlingua2_mbert",
        compressor_version="1-llmlingua-real",
    )
    assert segment.boundary_marker == expected_marker


def test_real_path_passes_target_budget_to_library(
    monkeypatch: pytest.MonkeyPatch, _install_llmlingua_stub: Any
) -> None:
    """target_budget threads through to PromptCompressor.compress_prompt."""
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "true")
    compressor = LLMLingua2mBERTCompressor()
    compressor.compress("hello", target_budget=7, trust_tier="facilitator")
    cached = llmlingua2_mbert._PROMPT_COMPRESSOR
    assert cached is not None
    assert cached.calls[0]["target_token"] == 7
    assert cached.calls[0]["use_token_level_filter"] is True


def test_real_path_lazy_loads_singleton(
    monkeypatch: pytest.MonkeyPatch, _install_llmlingua_stub: Any
) -> None:
    """First compress() loads the model; subsequent calls reuse the singleton."""
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "true")
    compressor = LLMLingua2mBERTCompressor()
    compressor.compress("hello", target_budget=1, trust_tier="participant_supplied")
    first_instance = llmlingua2_mbert._PROMPT_COMPRESSOR
    compressor.compress("world", target_budget=2, trust_tier="participant_supplied")
    second_instance = llmlingua2_mbert._PROMPT_COMPRESSOR
    assert first_instance is second_instance
    # Two calls -> two recorded compress_prompt entries on the SAME stub.
    assert len(first_instance.calls) == 2


def test_real_path_honours_phase2_gate_when_dep_present(
    monkeypatch: pytest.MonkeyPatch, _install_llmlingua_stub: Any
) -> None:
    """Phase 2 OFF + dep present -> still raises the phase-gate error."""
    monkeypatch.delenv("SACP_COMPRESSION_PHASE2_ENABLED", raising=False)
    compressor = LLMLingua2mBERTCompressor()
    with pytest.raises(NotImplementedError, match="Phase 2 not enabled"):
        compressor.compress("x", target_budget=1, trust_tier="participant_supplied")


def test_real_path_refuses_tier_one_regardless_of_dep(
    monkeypatch: pytest.MonkeyPatch, _install_llmlingua_stub: Any
) -> None:
    """FR-014 tier-1 refusal short-circuits before the dep import."""
    from src.compression.trust_tier import TierOneRefusalError

    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "true")
    compressor = LLMLingua2mBERTCompressor()
    with pytest.raises(TierOneRefusalError):
        compressor.compress("x", target_budget=1, trust_tier="system")
