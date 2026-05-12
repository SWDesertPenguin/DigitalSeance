# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 WebSocket event-shape + broadcast unit tests (T025 of tasks.md).

Covers the WS envelope shapes and the cross-instance broadcast helper
without requiring a live DB or running orchestrator. Endpoint-level
broadcast integration lives in tests/integration/ with the
@pytest.mark.integration marker.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.web_ui import cross_instance_broadcast, events

# ---------------------------------------------------------------------------
# Envelope shapes (contracts/ws-events.md)
# ---------------------------------------------------------------------------


def _make_event_payload() -> dict:
    return {
        "event_id": 1037,
        "event_class": "ai_question_opened",
        "event_class_label": "AI question opened",
        "participant_id": "p1",
        "trigger_snippet": "what should we do?",
        "trigger_snippet_truncated": False,
        "detector_score": 0.87,
        "turn_number": 14,
        "timestamp": "2026-05-11T14:32:01.234Z",
        "disposition": "pending",
    }


def test_detection_event_appended_envelope_shape() -> None:
    envelope = events.detection_event_appended_event(event=_make_event_payload())
    assert envelope["v"] == 1
    assert envelope["type"] == "detection_event_appended"
    assert envelope["event"]["event_id"] == 1037
    assert envelope["event"]["disposition"] == "pending"


def test_detection_event_resurfaced_envelope_shape() -> None:
    envelope = events.detection_event_resurfaced_event(
        event=_make_event_payload(),
        resurface_audit_row_id=2491,
    )
    assert envelope["type"] == "detection_event_resurfaced"
    assert envelope["resurface_audit_row_id"] == 2491
    assert envelope["event"]["event_id"] == 1037


def test_build_detection_event_payload_uses_registry_label() -> None:
    draft = events.DetectionEventDraft(
        session_id="s1",
        event_class="density_anomaly",
        participant_id="p1",
        trigger_snippet="x",
        detector_score=0.5,
        turn_number=10,
    )
    payload = events.build_detection_event_payload(draft, 42, "2026-05-11T00:00:00.000Z")
    assert payload["event_id"] == 42
    assert payload["event_class"] == "density_anomaly"
    assert payload["event_class_label"] == "Density anomaly"
    assert payload["disposition"] == "pending"
    assert payload["trigger_snippet_truncated"] is False


def test_build_detection_event_payload_unregistered_class_fallback() -> None:
    draft = events.DetectionEventDraft(
        session_id="s1",
        event_class="future_class_not_in_registry",
        participant_id="p1",
        trigger_snippet=None,
        detector_score=None,
        turn_number=None,
    )
    payload = events.build_detection_event_payload(draft, 1, "2026-05-11T00:00:00.000Z")
    assert payload["event_class_label"].startswith("[unregistered:")


# ---------------------------------------------------------------------------
# cross_instance_broadcast helpers
# ---------------------------------------------------------------------------


def test_channel_naming_per_session() -> None:
    assert cross_instance_broadcast._channel_for_session("abc") == "detection_events_abc"


def test_truncate_snippet_short_passes_through() -> None:
    envelope = {"event": {"trigger_snippet": "hello"}}
    out = cross_instance_broadcast._truncate_snippet(envelope)
    assert out["event"]["trigger_snippet"] == "hello"
    assert out["event"]["trigger_snippet_truncated"] is False


def test_truncate_snippet_long_truncates_to_limit() -> None:
    long = "x" * (cross_instance_broadcast.SNIPPET_NOTIFY_CHAR_LIMIT + 50)
    envelope = {"event": {"trigger_snippet": long}}
    out = cross_instance_broadcast._truncate_snippet(envelope)
    assert (
        len(out["event"]["trigger_snippet"]) == cross_instance_broadcast.SNIPPET_NOTIFY_CHAR_LIMIT
    )
    assert out["event"]["trigger_snippet_truncated"] is True


def test_truncate_snippet_non_string_passes_through() -> None:
    envelope = {"event": {"trigger_snippet": None}}
    out = cross_instance_broadcast._truncate_snippet(envelope)
    assert out["event"]["trigger_snippet"] is None
    assert out["event"]["trigger_snippet_truncated"] is False


# ---------------------------------------------------------------------------
# broadcast_session_event — same-instance path (no pool, no NOTIFY)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_session_event_same_instance_only_no_pool() -> None:
    """No pool means in-process broadcast only; cross-instance NOTIFY skipped."""
    envelope = {"event": {"trigger_snippet": "ok"}, "type": "detection_event_appended"}
    with patch.object(
        cross_instance_broadcast, "broadcast_to_session_roles", new=AsyncMock()
    ) as mock_bc:
        await cross_instance_broadcast.broadcast_session_event("sess1", envelope, pool=None)
        mock_bc.assert_awaited_once()
        args, kwargs = mock_bc.call_args
        assert args[0] == "sess1"
        assert kwargs["allow_roles"] == cross_instance_broadcast.FACILITATOR_ROLES


@pytest.mark.asyncio
async def test_broadcast_session_event_includes_truncation_flag() -> None:
    """The helper mutates the envelope to add trigger_snippet_truncated."""
    envelope = {"event": {"trigger_snippet": "ok"}}
    with patch.object(cross_instance_broadcast, "broadcast_to_session_roles", new=AsyncMock()):
        await cross_instance_broadcast.broadcast_session_event("sess1", envelope, pool=None)
    assert "trigger_snippet_truncated" in envelope["event"]
