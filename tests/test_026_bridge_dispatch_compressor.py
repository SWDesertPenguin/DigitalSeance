# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 T037 — bridge dispatch CompressorService.compress wiring.

The per-dispatch ``_invoke_compressor_pass`` helper in
``src/orchestrator/loop.py`` calls the process-scope CompressorService
on the assembled outgoing window before forwarding to the LiteLLM
adapter. Phase 1 default is NoOp — input verbatim, telemetry row
written. Phase 2 swaps the compressor via env var without touching the
dispatch call site.

These tests target the helper in isolation: assert the telemetry row
fires per dispatch (SC-013 invariant) AND that Phase 1 byte-identical
behaviour holds (no mutation of the ``messages`` list).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.compression import _telemetry_sink


@pytest.fixture(autouse=True)
def _clear_sink() -> None:
    _telemetry_sink.clear()


def _stub_speaker() -> SimpleNamespace:
    return SimpleNamespace(id="pp-test")


def test_invoke_compressor_pass_writes_telemetry_row() -> None:
    """SC-013: every dispatch writes one compression_log row."""
    from src.orchestrator.loop import _invoke_compressor_pass

    speaker = _stub_speaker()
    messages = [{"role": "system", "content": "you are an AI"}]
    _invoke_compressor_pass(speaker, messages, session_id="sess-1")
    records = _telemetry_sink.records()
    assert len(records) == 1
    assert records[0].compressor_id == "noop"
    assert records[0].session_id == "sess-1"
    assert records[0].participant_id == "pp-test"


def test_invoke_compressor_pass_does_not_mutate_messages() -> None:
    """SC-006: Phase 1 NoOp leaves the dispatched messages byte-identical."""
    from src.orchestrator.loop import _invoke_compressor_pass

    speaker = _stub_speaker()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user turn one"},
        {"role": "assistant", "content": "assistant reply"},
    ]
    expected = [dict(m) for m in messages]
    _invoke_compressor_pass(speaker, messages, session_id="sess-2")
    assert messages == expected


def test_invoke_compressor_pass_handles_list_content_blocks() -> None:
    """Anthropic cache_control payloads use list-of-blocks; the helper survives them."""
    from src.orchestrator.loop import _invoke_compressor_pass

    speaker = _stub_speaker()
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": "first block"},
                {"type": "text", "text": "second block"},
            ],
        },
    ]
    _invoke_compressor_pass(speaker, messages, session_id="sess-3")
    assert len(_telemetry_sink.records()) == 1


def test_invoke_compressor_pass_swallows_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-020 fail-soft: a broken compressor MUST NOT abort the dispatch path."""
    from src.compression import registry as registry_mod
    from src.orchestrator.loop import _invoke_compressor_pass

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic explosion")

    monkeypatch.setattr(registry_mod, "compress", _boom)
    _invoke_compressor_pass(_stub_speaker(), [{"role": "user", "content": "x"}], session_id="s")
    # No exception propagated — the helper swallowed via fail-soft.


def test_stringify_messages_round_trip() -> None:
    """The internal payload renderer keeps role + content tagged."""
    from src.orchestrator.loop import _stringify_messages

    out = _stringify_messages(
        [
            {"role": "system", "content": "system body"},
            {"role": "user", "content": "user body"},
        ],
    )
    assert "system: system body" in out
    assert "user: user body" in out
