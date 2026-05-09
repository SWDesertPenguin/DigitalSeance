# SPDX-License-Identifier: AGPL-3.0-or-later

"""v1 WS event helpers — shape tests that don't need a live DB.

Guards two Test06-Web06 regressions:
  * ``participant_removed`` event envelope (UI couldn't tell the row was
    gone and kept re-rejecting, getting 400s).
  * ``_participant_payload`` now carries ``spend_hourly`` so the UI can
    render an hourly-only cap instead of falling back to "(no cap)".
"""

from __future__ import annotations

from dataclasses import dataclass

from src.web_ui.events import (
    _participant_payload,
    participant_removed_event,
    participant_update_event,
)


@dataclass
class _P:
    id: str = "p1"
    session_id: str = "s1"
    display_name: str = "Alice"
    role: str = "participant"
    provider: str = "human"
    model: str = "human"
    model_tier: str = "n/a"
    model_family: str = "human"
    routing_preference: str = "always"
    status: str = "active"
    consecutive_timeouts: int = 0
    budget_hourly: float | None = None
    budget_daily: float | None = None
    max_tokens_per_turn: int | None = None
    invited_by: str | None = None


def test_participant_removed_event_shape() -> None:
    ev = participant_removed_event("abc123")
    assert ev == {"v": 1, "type": "participant_removed", "participant_id": "abc123"}


def test_participant_update_includes_hourly_spend_when_set() -> None:
    p = _P(budget_hourly=0.1, budget_daily=None)
    ev = participant_update_event(_participant_payload(p, spend_daily=0.0, spend_hourly=0.05))
    assert ev["type"] == "participant_update"
    assert ev["participant"]["budget_hourly"] == 0.1
    assert ev["participant"]["budget_daily"] is None
    assert ev["participant"]["spend_hourly"] == 0.05
    assert ev["participant"]["spend_daily"] == 0.0


def test_participant_payload_defaults_hourly_to_none() -> None:
    """Back-compat: callers that don't pass spend_hourly still get a valid shape."""
    p = _P(budget_daily=0.5)
    payload = _participant_payload(p, spend_daily=0.1)
    assert payload["spend_hourly"] is None
    assert payload["spend_daily"] == 0.1
