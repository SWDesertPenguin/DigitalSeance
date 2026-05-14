# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 §FR-024 — debug-export visibility reflection (T053)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from src.models.message import Message
from src.participant_api.tools.debug import _visibility_partition


def _msg(turn: int, visibility: str = "public") -> Message:
    return Message(
        turn_number=turn,
        session_id="s1",
        branch_id="main",
        parent_turn=None,
        speaker_id="anyone",
        speaker_type="ai",
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


def _participant(pid: str, provider: str = "openai"):
    return SimpleNamespace(id=pid, provider=provider, display_name=pid)


def test_visibility_partition_panel_ai_sees_public_only():
    """FR-024 — panel AI view excludes capcom_only rows."""
    msgs = [
        _msg(1, "public"),
        _msg(2, "capcom_only"),
        _msg(3, "public"),
    ]
    participants = [_participant("panel1"), _participant("c1")]
    session = SimpleNamespace(capcom_participant_id="c1")
    out = _visibility_partition(msgs, participants, session)
    assert out["panel1"] == [1, 3]
    assert out["c1"] == [1, 2, 3]


def test_visibility_partition_human_sees_all():
    """Humans have CAPCOM-or-broader visibility."""
    msgs = [_msg(1, "public"), _msg(2, "capcom_only")]
    participants = [_participant("h1", provider="human")]
    session = SimpleNamespace(capcom_participant_id="c1")
    out = _visibility_partition(msgs, participants, session)
    assert out["h1"] == [1, 2]


def test_visibility_partition_no_capcom_still_excludes_capcom_only():
    """FR-011 — historical capcom_only stays invisible to panel AIs after disable."""
    msgs = [_msg(1, "public"), _msg(2, "capcom_only")]
    participants = [_participant("panel1")]
    session = SimpleNamespace(capcom_participant_id=None)
    out = _visibility_partition(msgs, participants, session)
    assert out["panel1"] == [1]
