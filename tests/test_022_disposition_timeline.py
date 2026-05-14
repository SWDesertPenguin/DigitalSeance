# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 disposition timeline endpoint tests (T036 of tasks.md).

Covers ``GET /tools/admin/detection_events/<event_id>/timeline`` at the
handler-helper level:

- Authorization mirrors the page endpoint (facilitator-only +
  session-bound).
- Response shape projects ``log_repo.get_disposition_timeline`` rows to
  the wire format: ``{audit_row_id, action, facilitator_id, timestamp}``.
- Re-surface rows are preserved alongside disposition transitions in
  the timeline (per FR-006 + FR-010 — append-only, all transitions
  visible).
- Empty timeline yields an empty list (not a 404).

Append-only invariant verification (no UPDATE/DELETE on transition
rows) lives at the repo layer in ``test_022_log_repo.py`` and the
schema layer in alembic 017 — there is no UPDATE/DELETE SQL on the
admin_audit_log path here to assert against.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.participant_api.tools import detection_events as endpoint


def _make_participant(role: str = "facilitator", session_id: str = "s1"):
    """Lightweight Participant-shaped stub for the endpoint signature."""
    return SimpleNamespace(role=role, session_id=session_id, id="f1")


def _make_request(rows: list[dict]):
    """Construct a Request-like SimpleNamespace exposing state.log_repo."""
    log_repo = MagicMock()
    log_repo.get_disposition_timeline = AsyncMock(return_value=rows)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(log_repo=log_repo)))


# ---------------------------------------------------------------------------
# Authorization mirroring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeline_rejects_non_facilitator() -> None:
    """403 facilitator_only for participant role mismatch."""
    request = _make_request([])
    participant = _make_participant(role="ai")
    with pytest.raises(HTTPException) as excinfo:
        await endpoint.get_disposition_timeline(7, "s1", request, participant)
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_timeline_rejects_cross_session_facilitator() -> None:
    """403 facilitator_only for session id mismatch."""
    request = _make_request([])
    participant = _make_participant(session_id="other")
    with pytest.raises(HTTPException) as excinfo:
        await endpoint.get_disposition_timeline(7, "s1", request, participant)
    assert excinfo.value.status_code == 403


# ---------------------------------------------------------------------------
# Response projection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeline_projects_rows_to_wire_shape() -> None:
    """Repo rows ⇒ {audit_row_id, action, facilitator_id, timestamp} entries."""
    rows = [
        {
            "id": 11,
            "action": "detection_event_dismissed",
            "facilitator_id": "f1",
            "timestamp": datetime(2026, 5, 11, 14, 0, 0, tzinfo=UTC),
        },
        {
            "id": 12,
            "action": "detection_event_resurface",
            "facilitator_id": "f1",
            "timestamp": datetime(2026, 5, 11, 14, 5, 0, tzinfo=UTC),
        },
    ]
    request = _make_request(rows)
    participant = _make_participant()
    body = await endpoint.get_disposition_timeline(7, "s1", request, participant)
    assert body["event_id"] == 7
    assert len(body["transitions"]) == 2
    first = body["transitions"][0]
    assert first["audit_row_id"] == 11
    assert first["action"] == "detection_event_dismissed"
    assert first["facilitator_id"] == "f1"
    assert first["timestamp"] == "2026-05-11T14:00:00.000Z"


def _three_row_timeline() -> list[dict]:
    """Build a dismiss + resurface + acknowledge sequence for one event."""
    rows: list[dict] = []
    for i, action in enumerate(
        (
            "detection_event_dismissed",
            "detection_event_resurface",
            "detection_event_acknowledged",
        )
    ):
        rows.append(
            {
                "id": 11 + i,
                "action": action,
                "facilitator_id": "f1",
                "timestamp": datetime(2026, 5, 11, 14, i, 0, tzinfo=UTC),
            }
        )
    return rows


@pytest.mark.asyncio
async def test_timeline_preserves_resurface_rows_alongside_dispositions() -> None:
    """Re-surface entries appear alongside disposition transitions (FR-006)."""
    request = _make_request(_three_row_timeline())
    participant = _make_participant()
    body = await endpoint.get_disposition_timeline(7, "s1", request, participant)
    actions = [t["action"] for t in body["transitions"]]
    assert "detection_event_resurface" in actions
    assert "detection_event_dismissed" in actions
    assert "detection_event_acknowledged" in actions


@pytest.mark.asyncio
async def test_timeline_empty_rows_returns_empty_list() -> None:
    """Zero matching transitions ⇒ ``transitions: []`` (not 404)."""
    request = _make_request([])
    participant = _make_participant()
    body = await endpoint.get_disposition_timeline(7, "s1", request, participant)
    assert body == {"event_id": 7, "transitions": []}


@pytest.mark.asyncio
async def test_timeline_calls_repo_with_session_and_event_id() -> None:
    """Handler forwards the (session_id, event_id) pair to the repo verbatim."""
    request = _make_request([])
    participant = _make_participant()
    await endpoint.get_disposition_timeline(42, "s1", request, participant)
    request.app.state.log_repo.get_disposition_timeline.assert_awaited_once_with("s1", 42)
