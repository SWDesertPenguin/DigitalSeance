# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 resurface-endpoint unit tests (T034 of tasks.md).

Covers the non-DB unit surface of the FR-006 resurface POST handler:

- _build_resurface_envelope event-shape composition (registry label,
  ISO timestamp, audit_row_id propagation).
- _verify_session_active raises HTTP 409 on archived sessions and HTTP
  404 on missing sessions (FR-008).
- _lookup_event_row raises HTTP 404 on missing event id.

Full POST integration (DB INSERT into admin_audit_log + WS broadcast
emission) lives in tests/integration/ with the @pytest.mark.integration
marker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.mcp_server.tools import detection_events as endpoint


def _make_row() -> dict:
    return {
        "id": 1037,
        "session_id": "s1",
        "event_class": "ai_question_opened",
        "participant_id": "p1",
        "trigger_snippet": "what should we do?",
        "detector_score": 0.87,
        "turn_number": 14,
        "timestamp": datetime(2026, 5, 11, 14, 32, 1, 234000, tzinfo=UTC),
        "disposition": "banner_dismissed",
        "last_disposition_change_at": datetime(2026, 5, 11, 14, 32, 5, tzinfo=UTC),
    }


# ---------------------------------------------------------------------------
# _build_resurface_envelope
# ---------------------------------------------------------------------------


def test_build_resurface_envelope_carries_class_label() -> None:
    envelope = endpoint._build_resurface_envelope(_make_row(), audit_row_id=2491)
    assert envelope["type"] == "detection_event_resurfaced"
    assert envelope["resurface_audit_row_id"] == 2491
    assert envelope["event"]["event_class"] == "ai_question_opened"
    assert envelope["event"]["event_class_label"] == "AI question opened"


def test_build_resurface_envelope_preserves_disposition() -> None:
    """Per Clarifications §2: re-surface does NOT change disposition."""
    envelope = endpoint._build_resurface_envelope(_make_row(), audit_row_id=2491)
    assert envelope["event"]["disposition"] == "banner_dismissed"


def test_build_resurface_envelope_defaults_audit_id_to_zero() -> None:
    envelope = endpoint._build_resurface_envelope(_make_row())
    assert envelope["resurface_audit_row_id"] == 0


# ---------------------------------------------------------------------------
# _verify_session_active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_session_active_passes_for_active_session() -> None:
    state = SimpleNamespace(session_repo=MagicMock())
    state.session_repo.get_session = AsyncMock(return_value=SimpleNamespace(status="active"))
    await endpoint._verify_session_active(state, "s1")


@pytest.mark.asyncio
async def test_verify_session_active_raises_409_for_archived() -> None:
    state = SimpleNamespace(session_repo=MagicMock())
    state.session_repo.get_session = AsyncMock(return_value=SimpleNamespace(status="archived"))
    with pytest.raises(HTTPException) as excinfo:
        await endpoint._verify_session_active(state, "s1")
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail.get("error") == "session_archived"


@pytest.mark.asyncio
async def test_verify_session_active_raises_404_for_missing_session() -> None:
    state = SimpleNamespace(session_repo=MagicMock())
    state.session_repo.get_session = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as excinfo:
        await endpoint._verify_session_active(state, "s1")
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail.get("error") == "session_not_found"


# ---------------------------------------------------------------------------
# _lookup_event_row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_event_row_finds_matching_id() -> None:
    state = SimpleNamespace(log_repo=MagicMock())
    state.log_repo.get_detection_events_page = AsyncMock(return_value=[_make_row()])
    row = await endpoint._lookup_event_row(state, "s1", 1037)
    assert row["id"] == 1037


@pytest.mark.asyncio
async def test_lookup_event_row_raises_404_on_missing_event() -> None:
    state = SimpleNamespace(log_repo=MagicMock())
    state.log_repo.get_detection_events_page = AsyncMock(return_value=[_make_row()])
    with pytest.raises(HTTPException) as excinfo:
        await endpoint._lookup_event_row(state, "s1", 9999)
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail.get("error") == "event_not_found"
