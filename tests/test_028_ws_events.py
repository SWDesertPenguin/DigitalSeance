# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 — CAPCOM lifecycle WebSocket event payload tests (T016/T033/T038).

The helper ``_broadcast_capcom_event`` builds the event envelope and
broadcasts to every session subscriber. These tests pin the payload
shape against drift and confirm the broadcast scope is the facilitator's
session id (not derived from the outgoing participant — see the
session_id-not-from-out_id bug fixed during 028 closeout).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.participant_api.tools.session import _broadcast_capcom_event


def _request_with_participant(participant_id: str, display_name: str | None = "Alice"):
    request = MagicMock()
    if display_name is None:
        request.app.state.participant_repo.get_participant = AsyncMock(return_value=None)
    else:
        request.app.state.participant_repo.get_participant = AsyncMock(
            return_value=SimpleNamespace(
                id=participant_id,
                display_name=display_name,
                session_id="s1",
            ),
        )
    return request


@pytest.mark.asyncio
async def test_capcom_assigned_payload_shape(monkeypatch):
    """FR-007 / research.md §7 — assigned event carries id + display_name + timestamp."""
    captured: dict = {}

    async def capture(session_id: str, event: dict) -> None:
        captured["session_id"] = session_id
        captured["event"] = event

    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session", capture)
    await _broadcast_capcom_event(
        _request_with_participant("ai-1", "AI-1"),
        "s1",
        "capcom_assigned",
        "ai-1",
    )
    assert captured["session_id"] == "s1"
    event = captured["event"]
    assert event["v"] == 1
    assert event["type"] == "capcom_assigned"
    assert event["session_id"] == "s1"
    assert event["participant_id"] == "ai-1"
    assert event["display_name"] == "AI-1"
    assert event["timestamp"]  # ISO string, non-empty


@pytest.mark.asyncio
async def test_capcom_rotated_payload_shape(monkeypatch):
    """FR-008 — rotated event carries the new participant id + display name."""
    captured: dict = {}

    async def capture(session_id: str, event: dict) -> None:
        captured.update({"session_id": session_id, "event": event})

    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session", capture)
    await _broadcast_capcom_event(
        _request_with_participant("ai-2", "AI-2"),
        "s1",
        "capcom_rotated",
        "ai-2",
    )
    assert captured["event"]["type"] == "capcom_rotated"
    assert captured["event"]["participant_id"] == "ai-2"
    assert captured["event"]["display_name"] == "AI-2"


@pytest.mark.asyncio
async def test_capcom_disabled_payload_carries_session_id(monkeypatch):
    """FR-009 — disable broadcast targets the facilitator's session, not whoever
    happens to resolve from the outgoing participant id (the row may have
    transitioned by broadcast time).
    """
    captured: dict = {}

    async def capture(session_id: str, event: dict) -> None:
        captured.update({"session_id": session_id, "event": event})

    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session", capture)
    await _broadcast_capcom_event(
        _request_with_participant("ai-departed", None),  # outgoing already gone
        "s1",
        "capcom_disabled",
        "ai-departed",
    )
    assert captured["session_id"] == "s1"
    assert captured["event"]["type"] == "capcom_disabled"
    assert captured["event"]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_capcom_event_handles_null_participant(monkeypatch):
    """Departure cascades may pass participant_id=None — payload reflects that."""
    captured: dict = {}

    async def capture(session_id: str, event: dict) -> None:
        captured.update({"session_id": session_id, "event": event})

    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session", capture)
    request = MagicMock()
    request.app.state.participant_repo.get_participant = AsyncMock()
    await _broadcast_capcom_event(
        request,
        "s1",
        "capcom_departed_no_replacement",
        None,
    )
    assert captured["event"]["participant_id"] is None
    assert captured["event"]["display_name"] is None
    # When participant_id is None, the participant repo lookup is skipped.
    request.app.state.participant_repo.get_participant.assert_not_called()
