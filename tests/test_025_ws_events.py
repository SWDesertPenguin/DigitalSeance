"""Spec 025 WS event payload contracts (T071-T074 of tasks.md).

Pure unit tests for the `session_concluding` and `session_concluded`
event helpers in `src.web_ui.events`. End-to-end multi-client WS
broadcast tests (T074) need a running server + connected clients;
deferred to Phase 8 integration tests.

Covers FR-017, FR-018, FR-019:

- `session_concluding` payload shape (trigger_reason, trigger_value,
  remaining, trigger_fraction, at).
- `session_concluded` payload shape (pause_reason, summarizer_outcome,
  at).
- FR-019 cap-value-leak guard: payload MUST NOT include
  `length_cap_seconds` / `length_cap_turns`.
"""

from __future__ import annotations

from src.web_ui.events import session_concluded_event, session_concluding_event


def test_session_concluding_envelope_shape() -> None:
    out = session_concluding_event(
        trigger_reason="turns",
        trigger_value_turns=16,
        trigger_value_seconds=0,
        remaining_turns=4,
        remaining_seconds=None,
        trigger_fraction=0.80,
    )
    assert out["v"] == 1
    assert out["type"] == "session_concluding"
    assert out["trigger_reason"] == "turns"
    assert out["trigger_value"] == {"turns": 16, "seconds": 0}
    assert out["remaining"] == {"turns": 4, "seconds": None}
    assert out["trigger_fraction"] == 0.80
    assert "at" in out


def test_session_concluding_does_not_leak_cap_values() -> None:
    """FR-019: payload MUST NOT include the cap values themselves."""
    out = session_concluding_event(
        trigger_reason="time",
        trigger_value_turns=0,
        trigger_value_seconds=1440,
        remaining_turns=None,
        remaining_seconds=360,
        trigger_fraction=0.80,
    )
    assert "length_cap_seconds" not in out
    assert "length_cap_turns" not in out
    assert "length_cap_kind" not in out


def test_session_concluding_both_dimension() -> None:
    out = session_concluding_event(
        trigger_reason="both",
        trigger_value_turns=18,
        trigger_value_seconds=1500,
        remaining_turns=2,
        remaining_seconds=300,
        trigger_fraction=0.80,
    )
    assert out["trigger_reason"] == "both"
    assert out["remaining"]["turns"] == 2
    assert out["remaining"]["seconds"] == 300


def test_session_concluded_envelope_shape_auto_pause() -> None:
    out = session_concluded_event(pause_reason="auto_pause_on_cap", summarizer_outcome="success")
    assert out["v"] == 1
    assert out["type"] == "session_concluded"
    assert out["pause_reason"] == "auto_pause_on_cap"
    assert out["summarizer_outcome"] == "success"
    assert "at" in out


def test_session_concluded_envelope_shape_manual_stop() -> None:
    out = session_concluded_event(
        pause_reason="manual_stop_during_conclude", summarizer_outcome="failed_closed"
    )
    assert out["pause_reason"] == "manual_stop_during_conclude"
    assert out["summarizer_outcome"] == "failed_closed"


def test_session_concluded_does_not_leak_cap_values() -> None:
    out = session_concluded_event(pause_reason="auto_pause_on_cap", summarizer_outcome="success")
    assert "length_cap_seconds" not in out
    assert "length_cap_turns" not in out
