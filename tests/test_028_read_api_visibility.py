# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 §FR-006 — read-API visibility filtering tests.

The dispatch path (``ContextAssembler.assemble``) applies the filter.
This file covers the SECONDARY read paths that previously bypassed it:

  - ``GET /tools/participant/history``
  - ``GET /tools/participant/summary``
  - state_snapshot via ``build_state_snapshot``

All three apply the same ``_filter_visibility`` against the caller's
participant + the session's CAPCOM so a panel AI cannot poll its way
around the partition.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.message import Message
from src.participant_api.tools.participant import _apply_visibility
from src.web_ui.snapshot import _latest_summary, _recent_messages


def _msg(turn: int, visibility: str = "public", speaker_type: str = "ai") -> Message:
    return Message(
        turn_number=turn,
        session_id="s1",
        branch_id="main",
        parent_turn=None,
        speaker_id="anyone",
        speaker_type=speaker_type,
        delegated_from=None,
        complexity_score="trivial",
        content=f"t{turn}",
        token_count=1,
        cost_usd=None,
        created_at=datetime(2026, 5, 14),
        summary_epoch=None,
        kind="utterance",
        visibility=visibility,
    )


def _panel_participant():
    return SimpleNamespace(id="panel1", session_id="s1", provider="openai")


def _human_participant():
    return SimpleNamespace(id="human1", session_id="s1", provider="human")


def _capcom_participant():
    return SimpleNamespace(id="capcom1", session_id="s1", provider="openai")


def _request_with_capcom(capcom_id):
    request = MagicMock()
    request.app.state.session_repo.get_session = AsyncMock(
        return_value=SimpleNamespace(capcom_participant_id=capcom_id),
    )
    return request


@pytest.mark.asyncio
async def test_history_panel_ai_excludes_capcom_only():
    msgs = [_msg(1, "public"), _msg(2, "capcom_only"), _msg(3, "public")]
    out = await _apply_visibility(_request_with_capcom("capcom1"), _panel_participant(), msgs)
    assert [m.turn_number for m in out] == [1, 3]


@pytest.mark.asyncio
async def test_history_capcom_sees_everything():
    msgs = [_msg(1, "public"), _msg(2, "capcom_only")]
    out = await _apply_visibility(_request_with_capcom("capcom1"), _capcom_participant(), msgs)
    assert [m.turn_number for m in out] == [1, 2]


@pytest.mark.asyncio
async def test_history_human_sees_everything():
    msgs = [_msg(1, "public"), _msg(2, "capcom_only")]
    out = await _apply_visibility(_request_with_capcom("capcom1"), _human_participant(), msgs)
    assert [m.turn_number for m in out] == [1, 2]


@pytest.mark.asyncio
async def test_history_post_disable_still_filters_panel():
    """FR-011 — after disable, panel AIs still don't see historical capcom_only."""
    msgs = [_msg(1, "public"), _msg(2, "capcom_only")]
    out = await _apply_visibility(_request_with_capcom(None), _panel_participant(), msgs)
    assert [m.turn_number for m in out] == [1]


def _app_state_with_messages(rows: list[Message]):
    state = SimpleNamespace()
    state.message_repo = SimpleNamespace(
        get_recent=AsyncMock(return_value=rows),
        get_summaries=AsyncMock(return_value=rows),
    )
    state.pool = MagicMock()
    state.participant_repo = SimpleNamespace(get_participant=AsyncMock())
    return state


@pytest.mark.asyncio
async def test_snapshot_recent_messages_filters_panel(monkeypatch):
    msgs = [_msg(1, "public"), _msg(2, "capcom_only"), _msg(3, "public")]
    state = _app_state_with_messages(msgs)
    monkeypatch.setattr(
        "src.web_ui.snapshot.get_main_branch_id",
        AsyncMock(return_value="main"),
    )
    out = await _recent_messages(state, "s1", _panel_participant(), capcom_id="capcom1")
    assert [m["turn_number"] for m in out] == [1, 3]


@pytest.mark.asyncio
async def test_snapshot_recent_messages_unauth_recipient_strips_capcom_only(monkeypatch):
    """Unauthenticated WS subscribers (no participant_id) get the safer view."""
    msgs = [_msg(1, "public"), _msg(2, "capcom_only")]
    state = _app_state_with_messages(msgs)
    monkeypatch.setattr(
        "src.web_ui.snapshot.get_main_branch_id",
        AsyncMock(return_value="main"),
    )
    out = await _recent_messages(state, "s1", recipient=None, capcom_id="capcom1")
    assert [m["turn_number"] for m in out] == [1]


@pytest.mark.asyncio
async def test_snapshot_latest_summary_routes_panel_to_public(monkeypatch):
    """FR-018 — panel sees the public summary; capcom_only summary is filtered."""
    summaries = [
        _msg(10, visibility="public", speaker_type="summary"),
        _msg(10, visibility="capcom_only", speaker_type="summary"),
    ]
    state = _app_state_with_messages(summaries)
    monkeypatch.setattr(
        "src.web_ui.snapshot.get_main_branch_id",
        AsyncMock(return_value="main"),
    )
    out = await _latest_summary(state, "s1", _panel_participant(), capcom_id="capcom1")
    assert out is not None
    # The filter drops the capcom_only summary; the panel sees the public one.
    assert out["turn_number"] == 10
