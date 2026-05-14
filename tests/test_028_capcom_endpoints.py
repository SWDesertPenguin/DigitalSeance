# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 — CAPCOM lifecycle endpoint + repo tests (T013, T030, T036).

DB-bound: exercises the SessionRepository CAPCOM methods (assign / rotate /
disable) and the transactional invariants through a real PostgreSQL instance
via the per-test ``pool`` fixture. Pure-validation tests on the request
bodies live alongside in test_028_inject_handler.py.
"""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.auth.service import AuthService  # noqa: F401 — breaks an import cycle
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


_PARTICIPANT_KWARGS = {
    "provider": "openai",
    "model": "gpt-4o",
    "model_tier": "high",
    "model_family": "gpt",
    "context_window": 128000,
    "auto_approve": True,
}


async def _add_panel_ai(p_repo, session_id: str, display_name: str):
    p, _ = await p_repo.add_participant(
        session_id=session_id,
        display_name=display_name,
        **_PARTICIPANT_KWARGS,
    )
    return p


@pytest.fixture
async def session_with_panel(
    pool: asyncpg.Pool,
) -> tuple[SessionRepository, str, str, str, str]:
    """Build a session containing one facilitator + two AI participants."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Capcom Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    ai1 = await _add_panel_ai(p_repo, session.id, "AI-1")
    ai2 = await _add_panel_ai(p_repo, session.id, "AI-2")
    return session_repo, session.id, facilitator.id, ai1.id, ai2.id


async def test_assign_capcom_updates_session_and_participant(
    pool: asyncpg.Pool,
    session_with_panel,
):
    """FR-007 — assign sets routing_preference + capcom_participant_id."""
    session_repo, sid, _, ai1, _ = session_with_panel
    prior = await session_repo.assign_capcom(sid, ai1)
    assert prior == "always"
    session = await session_repo.get_session(sid)
    assert session.capcom_participant_id == ai1
    row = await pool.fetchval(
        "SELECT routing_preference FROM participants WHERE id = $1",
        ai1,
    )
    assert row == "capcom"


async def test_assign_capcom_second_attempt_violates_unique_index(
    pool: asyncpg.Pool,
    session_with_panel,
):
    """FR-005 — partial unique index rejects a second CAPCOM."""
    session_repo, sid, _, ai1, ai2 = session_with_panel
    await session_repo.assign_capcom(sid, ai1)
    with pytest.raises(asyncpg.UniqueViolationError):
        await session_repo.assign_capcom(sid, ai2)


async def test_rotate_capcom_swaps_atomically(
    pool: asyncpg.Pool,
    session_with_panel,
):
    """FR-008 + research.md §14 — sequential UPDATEs satisfy partial index."""
    session_repo, sid, _, ai1, ai2 = session_with_panel
    await session_repo.assign_capcom(sid, ai1)
    out_id, prior_new = await session_repo.rotate_capcom(
        sid,
        ai2,
        prior_routing_preference="always",
    )
    assert out_id == ai1
    assert prior_new == "always"
    session = await session_repo.get_session(sid)
    assert session.capcom_participant_id == ai2
    ai1_pref = await pool.fetchval(
        "SELECT routing_preference FROM participants WHERE id = $1",
        ai1,
    )
    ai2_pref = await pool.fetchval(
        "SELECT routing_preference FROM participants WHERE id = $1",
        ai2,
    )
    assert ai1_pref == "always"
    assert ai2_pref == "capcom"


async def test_disable_capcom_clears_assignment(
    pool: asyncpg.Pool,
    session_with_panel,
):
    """FR-009 — disable reverts routing_preference and NULLs the session column."""
    session_repo, sid, _, ai1, _ = session_with_panel
    await session_repo.assign_capcom(sid, ai1)
    out_id = await session_repo.disable_capcom(sid, prior_routing_preference="always")
    assert out_id == ai1
    session = await session_repo.get_session(sid)
    assert session.capcom_participant_id is None
    ai1_pref = await pool.fetchval(
        "SELECT routing_preference FROM participants WHERE id = $1",
        ai1,
    )
    assert ai1_pref == "always"


async def test_disable_no_capcom_returns_none(
    pool: asyncpg.Pool,
    session_with_panel,
):
    """Disable is a no-op when no CAPCOM is currently assigned."""
    session_repo, sid, _, _, _ = session_with_panel
    out_id = await session_repo.disable_capcom(sid, prior_routing_preference="always")
    assert out_id is None


async def test_assign_records_prior_routing_preference(
    pool: asyncpg.Pool,
    session_with_panel,
):
    """assign_capcom returns the prior value so the caller can audit + restore."""
    session_repo, sid, _, ai1, _ = session_with_panel
    await pool.execute(
        "UPDATE participants SET routing_preference = 'observer' WHERE id = $1",
        ai1,
    )
    prior = await session_repo.assign_capcom(sid, ai1)
    assert prior == "observer"


async def test_rotation_unique_index_resilient_under_repeated_swaps(
    pool: asyncpg.Pool,
    session_with_panel,
):
    """The partial unique index never trips on sequential rotation."""
    session_repo, sid, _, ai1, ai2 = session_with_panel
    await session_repo.assign_capcom(sid, ai1)
    await session_repo.rotate_capcom(sid, ai2, prior_routing_preference="always")
    await session_repo.rotate_capcom(sid, ai1, prior_routing_preference="always")
    await session_repo.rotate_capcom(sid, ai2, prior_routing_preference="always")
    session = await session_repo.get_session(sid)
    assert session.capcom_participant_id == ai2
