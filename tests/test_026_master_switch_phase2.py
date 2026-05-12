# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 T051 — master-switch-off canary.

With ``SACP_COMPRESSION_PHASE2_ENABLED=false`` (default) AND
``SACP_COMPRESSION_DEFAULT_COMPRESSOR=noop`` (default), every dispatch
MUST write a ``compression_log`` row with ``compressor_id='noop'`` and
MUST behave byte-identically to the un-compressor-mediated baseline
(SC-006).
"""

from __future__ import annotations

import pytest

from src.compression import _telemetry_sink
from src.compression import registry as compressor_registry


@pytest.fixture(autouse=True)
def _clear_sink_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _telemetry_sink.clear()
    for name in (
        "SACP_COMPRESSION_DEFAULT_COMPRESSOR",
        "SACP_COMPRESSION_PHASE2_ENABLED",
        "SACP_TOPOLOGY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_master_switch_off_dispatch_writes_noop_telemetry_row() -> None:
    """Defaults select NoOp; compression_log row carries compressor_id='noop'."""
    compressor_registry.compress(
        "payload",
        target_budget=100,
        trust_tier="participant_supplied",
        session_id="sess-canary",
        participant_id="pp-canary",
        turn_id="turn-canary",
    )
    records = _telemetry_sink.records()
    assert len(records) == 1
    assert records[0].compressor_id == "noop"
    assert records[0].layer == "noop"


def test_master_switch_off_dispatch_is_byte_identical_to_input() -> None:
    """SC-006 baseline parity: NoOp returns input verbatim."""
    from src.compression.noop import NoOpCompressor

    payload = "hello world this is some content"
    segment = NoOpCompressor().compress(
        payload, target_budget=999, trust_tier="participant_supplied"
    )
    assert segment.output_text == payload
    assert segment.boundary_marker is None


def test_phase2_disabled_env_blocks_llmlingua_real_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2 gate: SACP_COMPRESSION_PHASE2_ENABLED unset/false leaves Layer 4 cold."""
    from src.compression.llmlingua2_mbert import LLMLingua2mBERTCompressor

    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "false")
    with pytest.raises(NotImplementedError, match="SACP_COMPRESSION_PHASE2_ENABLED"):
        LLMLingua2mBERTCompressor().compress(
            "payload",
            target_budget=100,
            trust_tier="participant_supplied",
        )


def test_default_compressor_resolves_to_noop_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SACP_COMPRESSION_DEFAULT_COMPRESSOR unset -> dispatch picks 'noop'."""
    monkeypatch.delenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", raising=False)
    compressor_registry.compress(
        "payload",
        target_budget=100,
        trust_tier="participant_supplied",
        session_id="s",
        participant_id="p",
        turn_id="t",
    )
    assert _telemetry_sink.records()[0].compressor_id == "noop"
