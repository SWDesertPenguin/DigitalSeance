"""Unit tests for src.orchestrator.announcements — system departure messages."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.announcements import announce_departure


def _fake_msg(content: str = "MiniA was removed by the facilitator."):
    return MagicMock(
        turn_number=42,
        speaker_id="fac1",
        speaker_type="system",
        content=content,
        token_count=10,
        created_at=datetime(2026, 4, 26, 0, 0, 0),
        summary_epoch=None,
    )


async def _call_announce(msg_repo, bcast, **overrides):
    """Run announce_departure with patched branch + websocket."""
    with (
        patch("src.orchestrator.announcements.get_main_branch_id", AsyncMock(return_value="main")),
        patch("src.web_ui.websocket.broadcast_to_session", bcast),
    ):
        kwargs = {
            "pool": MagicMock(),
            "msg_repo": msg_repo,
            "session_id": "s1",
            "speaker_id": "fac1",
            "departing_name": "MiniA",
            "kind": "was removed by the facilitator",
        }
        kwargs.update(overrides)
        await announce_departure(**kwargs)


@pytest.mark.asyncio
async def test_announce_departure_writes_system_row():
    """Helper appends speaker_type='system' message with the assembled content."""
    msg_repo = MagicMock()
    msg_repo.append_message = AsyncMock(return_value=_fake_msg())
    await _call_announce(msg_repo, AsyncMock())
    kwargs = msg_repo.append_message.await_args.kwargs
    assert kwargs["speaker_type"] == "system"
    assert kwargs["speaker_id"] == "fac1"
    assert kwargs["session_id"] == "s1"
    assert kwargs["content"] == "MiniA was removed by the facilitator."


@pytest.mark.asyncio
async def test_announce_departure_broadcasts_message_event():
    """Helper emits a v1 'message' event so live subscribers see the notice."""
    msg_repo = MagicMock()
    msg_repo.append_message = AsyncMock(return_value=_fake_msg())
    bcast = AsyncMock()
    await _call_announce(msg_repo, bcast)
    bcast.assert_awaited_once()
    sent_session_id, event = bcast.await_args.args
    assert sent_session_id == "s1"
    assert event["type"] == "message"
    assert event["message"]["speaker_type"] == "system"


@pytest.mark.asyncio
async def test_announce_departure_token_count_at_least_one():
    """Even an empty kind string yields token_count >= 1 (NOT NULL column)."""
    msg_repo = MagicMock()
    msg_repo.append_message = AsyncMock(return_value=_fake_msg("X ."))
    await _call_announce(
        msg_repo,
        AsyncMock(),
        speaker_id="x",
        departing_name="X",
        kind="",
    )
    assert msg_repo.append_message.await_args.kwargs["token_count"] >= 1
