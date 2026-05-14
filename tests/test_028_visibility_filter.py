# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 §FR-006 — visibility filter unit tests.

The filter is a pure function. These tests exercise its branches without
spinning up a DB; the DB-bound behavior (the assembler wiring) is covered
by the integration tests added in Phase 3.
"""

from __future__ import annotations

from datetime import datetime

from src.models.message import Message
from src.models.participant import Participant
from src.orchestrator.context import _filter_visibility


def _msg(turn: int, speaker_id: str, visibility: str = "public") -> Message:
    return Message(
        turn_number=turn,
        session_id="s1",
        branch_id="main",
        parent_turn=None,
        speaker_id=speaker_id,
        speaker_type="ai",
        delegated_from=None,
        complexity_score="trivial",
        content=f"turn {turn}",
        token_count=10,
        cost_usd=None,
        created_at=datetime(2026, 5, 14),
        summary_epoch=None,
        kind="utterance",
        visibility=visibility,
    )


_PARTICIPANT_DEFAULTS: dict = {
    "session_id": "s1",
    "role": "participant",
    "model": "claude-sonnet-4-6",
    "model_tier": "mid",
    "prompt_tier": "mid",
    "model_family": "claude",
    "context_window": 200000,
    "supports_tools": True,
    "supports_streaming": True,
    "domain_tags": "[]",
    "routing_preference": "always",
    "observer_interval": 10,
    "burst_interval": 20,
    "review_gate_timeout": 600,
    "turns_since_last_burst": 0,
    "turn_timeout_seconds": 60,
    "consecutive_timeouts": 0,
    "status": "active",
    "budget_hourly": None,
    "budget_daily": None,
    "max_tokens_per_turn": None,
    "cost_per_input_token": None,
    "cost_per_output_token": None,
    "system_prompt": "",
    "api_endpoint": None,
    "api_key_encrypted": None,
    "auth_token_hash": None,
    "last_seen": None,
    "invited_by": None,
    "approved_at": None,
    "token_expires_at": None,
    "bound_ip": None,
}


def _participant(pid: str, provider: str = "anthropic") -> Participant:
    return Participant(id=pid, display_name=pid, provider=provider, **_PARTICIPANT_DEFAULTS)


def test_no_capcom_assigned_returns_messages_unchanged():
    """When capcom_id is None, no filtering occurs (pre-feature behavior)."""
    msgs = [_msg(1, "p1"), _msg(2, "p2", visibility="capcom_only")]
    out = _filter_visibility(msgs, _participant("p1"), capcom_id=None)
    assert out == msgs


def test_capcom_participant_sees_all_messages():
    """The active CAPCOM AI sees both public and capcom_only messages."""
    msgs = [
        _msg(1, "p1", visibility="public"),
        _msg(2, "p2", visibility="capcom_only"),
    ]
    out = _filter_visibility(msgs, _participant("capcom1"), capcom_id="capcom1")
    assert out == msgs


def test_human_participant_sees_all_messages():
    """Humans hold CAPCOM-or-broader visibility (no filtering)."""
    msgs = [
        _msg(1, "p1", visibility="public"),
        _msg(2, "p2", visibility="capcom_only"),
    ]
    out = _filter_visibility(
        msgs,
        _participant("human1", provider="human"),
        capcom_id="capcom1",
    )
    assert out == msgs


def test_panel_ai_excludes_capcom_only_messages():
    """Non-CAPCOM AI participants only see public messages."""
    msgs = [
        _msg(1, "p1", visibility="public"),
        _msg(2, "p2", visibility="capcom_only"),
        _msg(3, "p3", visibility="public"),
    ]
    out = _filter_visibility(
        msgs,
        _participant("panel1"),
        capcom_id="capcom1",
    )
    assert [m.turn_number for m in out] == [1, 3]
    assert all(m.visibility == "public" for m in out)


def test_filter_preserves_order():
    """Filter is order-stable (relative order of survivors unchanged)."""
    msgs = [
        _msg(1, "p1", visibility="public"),
        _msg(2, "p2", visibility="capcom_only"),
        _msg(3, "p3", visibility="public"),
        _msg(4, "p4", visibility="capcom_only"),
        _msg(5, "p5", visibility="public"),
    ]
    out = _filter_visibility(msgs, _participant("panel1"), capcom_id="capcom1")
    assert [m.turn_number for m in out] == [1, 3, 5]


def test_empty_input_returns_empty():
    out = _filter_visibility([], _participant("p1"), capcom_id="capcom1")
    assert out == []


def test_default_message_visibility_is_public():
    """Spec 028 §FR-001 — default Message.visibility is 'public'.

    Guards against accidental defaults drift that would silently make
    every new message invisible to panel AIs.
    """
    m = Message(
        turn_number=0,
        session_id="s1",
        branch_id="main",
        parent_turn=None,
        speaker_id="p1",
        speaker_type="ai",
        delegated_from=None,
        complexity_score="trivial",
        content="hi",
        token_count=1,
        cost_usd=None,
        created_at=datetime(2026, 5, 14),
        summary_epoch=None,
    )
    assert m.visibility == "public"
    assert m.kind == "utterance"
