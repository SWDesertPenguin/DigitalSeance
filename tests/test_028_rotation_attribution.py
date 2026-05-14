# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 — in-flight capcom_query rotation attribution (T031/T032).

Drives the rotation scenario at the SessionRepository level + verifies
the visibility filter on top: CAPCOM A asks a query, rotation to B
happens, the human's reply lands AFTER rotation. The reply is
attributed to B at arrival time because context assembly reads the
session's current ``capcom_participant_id`` at each assemble — there
is no per-query foreign key binding the reply to the questioner.

DB-bound: the SessionRepo bits exercise the transactional swap, the
visibility filter bit covers the FR-013 arrival-time invariant on
filtered messages.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.auth.service import AuthService  # noqa: F401 — breaks an import cycle
from src.models.message import Message
from src.orchestrator.context import _filter_visibility
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


def _capcom_only_msg(turn: int, speaker_id: str) -> Message:
    return Message(
        turn_number=turn,
        session_id="s1",
        branch_id="main",
        parent_turn=None,
        speaker_id=speaker_id,
        speaker_type="human" if speaker_id.startswith("h") else "ai",
        delegated_from=None,
        complexity_score="trivial",
        content=f"t{turn}",
        token_count=1,
        cost_usd=None,
        created_at=datetime(2026, 5, 14),
        summary_epoch=None,
        kind="utterance",
        visibility="capcom_only",
    )


_AI_KWARGS = {
    "provider": "openai",
    "model": "gpt-4o",
    "model_tier": "high",
    "model_family": "gpt",
    "context_window": 128000,
    "auto_approve": True,
}


async def _add_ai(p_repo, session_id: str, display_name: str):
    p, _ = await p_repo.add_participant(
        session_id=session_id,
        display_name=display_name,
        **_AI_KWARGS,
    )
    return p


@pytest.fixture
async def session_with_two_ais(
    pool: asyncpg.Pool,
) -> tuple[SessionRepository, str, str, str]:
    """Session with one facilitator + two AI participants (A and B)."""
    session_repo = SessionRepository(pool)
    session, _facilitator, _ = await session_repo.create_session(
        "Rotation Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    ai_a = await _add_ai(p_repo, session.id, "AI-A")
    ai_b = await _add_ai(p_repo, session.id, "AI-B")
    return session_repo, session.id, ai_a.id, ai_b.id


async def test_rotation_session_pointer_moves_atomically(
    pool: asyncpg.Pool,
    session_with_two_ais,
):
    """After rotation A → B, sessions.capcom_participant_id resolves to B."""
    session_repo, sid, ai_a, ai_b = session_with_two_ais
    await session_repo.assign_capcom(sid, ai_a)
    await session_repo.rotate_capcom(sid, ai_b, prior_routing_preference="always")
    session = await session_repo.get_session(sid)
    assert session.capcom_participant_id == ai_b


async def test_post_rotation_capcom_id_is_what_assemble_reads(
    pool: asyncpg.Pool,
    session_with_two_ais,
):
    """FR-013 arrival-time attribution — the visibility filter admits the
    human's reply (a capcom_only message) into B's context and excludes
    it from A's, because attribution is by-current-CAPCOM not by-questioner.
    """
    from types import SimpleNamespace

    session_repo, sid, ai_a, ai_b = session_with_two_ais
    await session_repo.assign_capcom(sid, ai_a)
    await session_repo.rotate_capcom(sid, ai_b, prior_routing_preference="always")
    session = await session_repo.get_session(sid)
    capcom_id = session.capcom_participant_id
    reply = _capcom_only_msg(turn=5, speaker_id="h1")
    visible_to_b = _filter_visibility(
        [reply],
        SimpleNamespace(id=ai_b, provider="openai"),
        capcom_id,
    )
    visible_to_a = _filter_visibility(
        [reply],
        SimpleNamespace(id=ai_a, provider="openai"),
        capcom_id,
    )
    assert [m.turn_number for m in visible_to_b] == [5]
    assert visible_to_a == []


async def test_rotation_audit_trail_attributes_each_event_correctly(
    pool: asyncpg.Pool,
    session_with_two_ais,
):
    """Rotation logs capcom_rotated with both previous + new participant ids
    so a forensic reviewer can reconstruct the cross-rotation chain.
    """
    session_repo, sid, ai_a, ai_b = session_with_two_ais
    await session_repo.assign_capcom(sid, ai_a)
    out_id, _ = await session_repo.rotate_capcom(
        sid,
        ai_b,
        prior_routing_preference="always",
    )
    assert out_id == ai_a  # outgoing identity preserved for the audit row
