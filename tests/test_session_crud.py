# SPDX-License-Identifier: AGPL-3.0-or-later

"""US1: Facilitator creates a session — atomic creation and query tests."""

from __future__ import annotations

import asyncpg
import pytest

from src.repositories.session_repo import SessionRepository


@pytest.fixture
def repo(pool: asyncpg.Pool) -> SessionRepository:
    """Provide a SessionRepository backed by the test pool."""
    return SessionRepository(pool)


async def test_create_session_returns_session_participant_branch(
    repo: SessionRepository,
) -> None:
    """Session creation returns a session, facilitator, and main branch."""
    session, participant, branch = await repo.create_session(
        "Test Session",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )

    assert session.name == "Test Session"
    assert session.status == "active"
    assert session.current_turn == 0
    assert session.facilitator_id == participant.id

    assert participant.role == "facilitator"
    assert participant.display_name == "Alice"
    assert participant.provider == "anthropic"
    assert participant.model_family == "claude"

    assert branch.id.startswith("main-")
    assert branch.session_id == session.id
    assert branch.name == "main"
    assert branch.parent_branch_id is None


async def test_update_name_renames_session(repo: SessionRepository) -> None:
    """update_name persists a new session name and echoes it back."""
    session, _, _ = await repo.create_session(
        "Original",
        facilitator_display_name="A",
        facilitator_provider="human",
        facilitator_model="human",
        facilitator_model_tier="n/a",
        facilitator_model_family="human",
        facilitator_context_window=0,
    )
    updated = await repo.update_name(session.id, "Renamed")
    assert updated.name == "Renamed"
    refetched = await repo.get_session(session.id)
    assert refetched is not None
    assert refetched.name == "Renamed"


async def test_update_name_rejects_blank(repo: SessionRepository) -> None:
    """update_name refuses empty names and whitespace-only strings."""
    session, _, _ = await repo.create_session(
        "X",
        facilitator_display_name="A",
        facilitator_provider="human",
        facilitator_model="human",
        facilitator_model_tier="n/a",
        facilitator_model_family="human",
        facilitator_context_window=0,
    )
    with pytest.raises(ValueError, match="blank"):
        await repo.update_name(session.id, "   ")


async def test_create_session_defaults(
    repo: SessionRepository,
) -> None:
    """Session creation applies correct defaults."""
    session, _, _ = await repo.create_session(
        "Defaults Test",
        facilitator_display_name="Bob",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )

    assert session.cadence_preset == "cruise"
    assert session.acceptance_mode == "unanimous"
    assert session.min_model_tier == "low"
    assert session.auto_approve is False
    assert session.auto_archive_days is None
    assert session.auto_delete_days is None


async def test_get_session_returns_created_session(
    repo: SessionRepository,
) -> None:
    """get_session retrieves a previously created session."""
    created, _, _ = await repo.create_session(
        "Retrieve Test",
        facilitator_display_name="Carol",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )

    fetched = await repo.get_session(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Retrieve Test"


async def test_get_session_returns_none_for_unknown(
    repo: SessionRepository,
) -> None:
    """get_session returns None for a nonexistent ID."""
    result = await repo.get_session("nonexistent-id")
    assert result is None


async def test_list_sessions_returns_all(
    repo: SessionRepository,
) -> None:
    """list_sessions returns all sessions when no filter is applied."""
    await repo.create_session(
        "List Test 1",
        facilitator_display_name="Dave",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )
    await repo.create_session(
        "List Test 2",
        facilitator_display_name="Eve",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )

    sessions = await repo.list_sessions()
    names = {s.name for s in sessions}
    assert "List Test 1" in names
    assert "List Test 2" in names
