# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 backend filter-composition integration tests (T043 of tasks.md).

Per FR-011 + research.md §8, filtering is client-side in v1: the server
returns one page of events and the SPA narrows the visible set across
the four filter axes (type / participant / time-range / disposition).
This test asserts the SERVER side of that contract — the GET endpoint
returns all five event classes, all participants, and all dispositions
in a single response so the client never needs a second fetch to
compute filter axis values or apply AND composition.

What's covered:

- The page response includes one row per event class when the repo
  returns a heterogeneous set (the endpoint MUST NOT drop classes).
- The page response carries every distinct participant_id (the SPA
  derives the participant filter dropdown from the loaded set; the
  server doesn't paginate by participant).
- The page response carries every distinct disposition value (the
  disposition filter dropdown is populated from the same loaded set).
- ``count`` reflects the total events returned (NOT a filter-applied
  count); the client decrements via ``hiddenByAxis`` per axis.
- ``max_events_applied`` is True only when the LIMIT capped the
  result set — telling the SPA there may be more events beyond the
  cap.

The pure-logic AND-composition implementation lives in
``frontend/detection_history_filters.js`` and is exercised under Node
at ``tests/frontend/test_detection_history_filters.js``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mcp_server.tools import detection_events as endpoint


def _row(
    *,
    row_id: int,
    event_class: str,
    participant_id: str,
    disposition: str = "pending",
    minutes_ago: int = 0,
) -> dict:
    """Build a detection_events row matching the alembic 017 column set."""
    return {
        "id": row_id,
        "session_id": "s1",
        "event_class": event_class,
        "participant_id": participant_id,
        "trigger_snippet": f"snippet for {event_class}",
        "detector_score": 0.5,
        "turn_number": 3,
        "timestamp": datetime.now(UTC) - timedelta(minutes=minutes_ago),
        "disposition": disposition,
        "last_disposition_change_at": None,
    }


def _make_request(rows: list[dict]):
    """Wrap ``rows`` into a Request-like SimpleNamespace exposing log_repo."""
    log_repo = MagicMock()
    log_repo.get_detection_events_page = AsyncMock(return_value=rows)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(log_repo=log_repo)))


def _make_participant():
    return SimpleNamespace(role="facilitator", session_id="s1", id="f1")


# ---------------------------------------------------------------------------
# All five event classes survive the endpoint round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_returns_all_five_event_classes() -> None:
    """No class is filtered out server-side — the panel decides what to hide."""
    rows = [
        _row(row_id=1, event_class="ai_question_opened", participant_id="ai1"),
        _row(row_id=2, event_class="ai_exit_requested", participant_id="ai2"),
        _row(row_id=3, event_class="density_anomaly", participant_id="ai1"),
        _row(row_id=4, event_class="mode_recommendation", participant_id="f1"),
        _row(row_id=5, event_class="mode_change", participant_id="f1"),
    ]
    request = _make_request(rows)
    body = await endpoint.get_detection_events(request, "s1", _make_participant())
    classes_seen = {e["event_class"] for e in body["events"]}
    assert classes_seen == {
        "ai_question_opened",
        "ai_exit_requested",
        "density_anomaly",
        "mode_recommendation",
        "mode_change",
    }
    assert body["count"] == 5


# ---------------------------------------------------------------------------
# Participant-id axis comes from the loaded set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_preserves_distinct_participant_ids() -> None:
    """SPA derives participant filter from the response — server must surface every id."""
    rows = [
        _row(row_id=1, event_class="ai_question_opened", participant_id="ai1"),
        _row(row_id=2, event_class="ai_exit_requested", participant_id="ai2"),
        _row(row_id=3, event_class="density_anomaly", participant_id="ai3"),
    ]
    request = _make_request(rows)
    body = await endpoint.get_detection_events(request, "s1", _make_participant())
    participants_seen = {e["participant_id"] for e in body["events"]}
    assert participants_seen == {"ai1", "ai2", "ai3"}


# ---------------------------------------------------------------------------
# Disposition axis comes from the loaded set
# ---------------------------------------------------------------------------


def _rows_one_per_disposition() -> list[dict]:
    """Build four rows, one per disposition enum value."""
    classes = [
        "ai_question_opened",
        "ai_exit_requested",
        "density_anomaly",
        "mode_recommendation",
    ]
    dispositions = ["pending", "banner_acknowledged", "banner_dismissed", "auto_resolved"]
    return [
        _row(row_id=i + 1, event_class=cls, participant_id="ai1", disposition=disp)
        for i, (cls, disp) in enumerate(zip(classes, dispositions, strict=True))
    ]


@pytest.mark.asyncio
async def test_endpoint_preserves_all_four_disposition_values() -> None:
    """All four enum values surface in the response — SPA uses them as filter axes."""
    request = _make_request(_rows_one_per_disposition())
    body = await endpoint.get_detection_events(request, "s1", _make_participant())
    dispositions_seen = {e["disposition"] for e in body["events"]}
    assert dispositions_seen == {
        "pending",
        "banner_acknowledged",
        "banner_dismissed",
        "auto_resolved",
    }


# ---------------------------------------------------------------------------
# count and max_events_applied for the SPA's filter math
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_reflects_total_returned_rows() -> None:
    """``count`` is the page size pre-filter (client narrows via hiddenByAxis)."""
    rows = [
        _row(row_id=i, event_class="ai_question_opened", participant_id="ai1") for i in range(1, 11)
    ]
    request = _make_request(rows)
    body = await endpoint.get_detection_events(request, "s1", _make_participant())
    assert body["count"] == 10


@pytest.mark.asyncio
async def test_max_events_applied_false_when_no_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """No cap configured ⇒ max_events_applied=False regardless of row count."""
    monkeypatch.delenv("SACP_DETECTION_HISTORY_MAX_EVENTS", raising=False)
    rows = [
        _row(row_id=1, event_class="ai_question_opened", participant_id="ai1"),
    ]
    request = _make_request(rows)
    body = await endpoint.get_detection_events(request, "s1", _make_participant())
    assert body["max_events_applied"] is False


@pytest.mark.asyncio
async def test_max_events_applied_true_when_response_equals_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cap reached ⇒ max_events_applied=True (SPA may surface 'more available' hint)."""
    monkeypatch.setenv("SACP_DETECTION_HISTORY_MAX_EVENTS", "2")
    rows = [
        _row(row_id=1, event_class="ai_question_opened", participant_id="ai1"),
        _row(row_id=2, event_class="ai_exit_requested", participant_id="ai2"),
    ]
    request = _make_request(rows)
    body = await endpoint.get_detection_events(request, "s1", _make_participant())
    assert body["max_events_applied"] is True


# ---------------------------------------------------------------------------
# Cross-axis composition seed — heterogeneous set passes through unchanged
# ---------------------------------------------------------------------------


def _heterogeneous_session_rows() -> list[dict]:
    """Four-row mix spanning class, participant, disposition, and timestamp axes."""
    return [
        _row(row_id=1, event_class="ai_question_opened", participant_id="ai1"),
        _row(
            row_id=2,
            event_class="ai_question_opened",
            participant_id="ai2",
            disposition="banner_dismissed",
            minutes_ago=1,
        ),
        _row(
            row_id=3,
            event_class="density_anomaly",
            participant_id="ai1",
            disposition="auto_resolved",
            minutes_ago=2,
        ),
        _row(
            row_id=4,
            event_class="mode_change",
            participant_id="f1",
            disposition="banner_acknowledged",
            minutes_ago=3,
        ),
    ]


@pytest.mark.asyncio
async def test_heterogeneous_session_returns_all_axes_intact() -> None:
    """A session spanning every axis combination keeps every row in one page."""
    request = _make_request(_heterogeneous_session_rows())
    body = await endpoint.get_detection_events(request, "s1", _make_participant())
    assert body["count"] == 4
    seen_classes = {e["event_class"] for e in body["events"]}
    seen_participants = {e["participant_id"] for e in body["events"]}
    seen_dispositions = {e["disposition"] for e in body["events"]}
    assert len(seen_classes) >= 3
    assert seen_participants == {"ai1", "ai2", "f1"}
    assert seen_dispositions == {
        "pending",
        "banner_dismissed",
        "auto_resolved",
        "banner_acknowledged",
    }
