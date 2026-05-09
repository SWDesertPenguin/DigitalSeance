# SPDX-License-Identifier: AGPL-3.0-or-later

"""US2: Participant joins — config persistence and encryption tests."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def session_id(pool: asyncpg.Pool) -> str:
    """Create a session and return its ID for participant tests."""
    repo = SessionRepository(pool)
    session, _, _ = await repo.create_session(
        "Participant Test Session",
        facilitator_display_name="Facilitator",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id


@pytest.fixture
def repo(pool: asyncpg.Pool) -> ParticipantRepository:
    """Provide a ParticipantRepository with a test encryption key."""
    return ParticipantRepository(pool, encryption_key=TEST_KEY)


async def test_add_participant_persists_config(
    repo: ParticipantRepository,
    session_id: str,
) -> None:
    """All configuration fields persist correctly."""
    participant, _ = await repo.add_participant(
        session_id=session_id,
        display_name="Alice",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auto_approve=True,
    )

    assert participant.display_name == "Alice"
    assert participant.provider == "openai"
    assert participant.model == "gpt-4o"
    assert participant.model_tier == "high"
    assert participant.model_family == "gpt"
    assert participant.context_window == 128000
    assert participant.role == "participant"


async def test_add_participant_encrypts_api_key(
    repo: ParticipantRepository,
    session_id: str,
) -> None:
    """API key is Fernet-encrypted at rest — not plaintext."""
    plaintext_key = "sk-test-secret-key-12345"
    participant, _ = await repo.add_participant(
        session_id=session_id,
        display_name="Bob",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        api_key=plaintext_key,
    )

    assert participant.api_key_encrypted is not None
    assert participant.api_key_encrypted != plaintext_key
    # Verify it decrypts correctly
    fernet = Fernet(TEST_KEY.encode())
    decrypted = fernet.decrypt(
        participant.api_key_encrypted.encode(),
    ).decode()
    assert decrypted == plaintext_key


async def test_add_participant_hashes_auth_token(
    repo: ParticipantRepository,
    session_id: str,
) -> None:
    """Auth token is stored as bcrypt hash only."""
    import bcrypt

    token = "test-auth-token-abc123"  # noqa: S105
    participant, returned_token = await repo.add_participant(
        session_id=session_id,
        display_name="Carol",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        model_tier="high",
        model_family="claude",
        context_window=200000,
        auth_token=token,
    )

    assert participant.auth_token_hash is not None
    assert participant.auth_token_hash != token
    assert returned_token == token
    # Verify bcrypt hash matches
    assert bcrypt.checkpw(
        token.encode(),
        participant.auth_token_hash.encode(),
    )


async def test_add_participant_pending_without_auto_approve(
    repo: ParticipantRepository,
    session_id: str,
) -> None:
    """Participant starts as 'pending' when auto_approve is False."""
    participant, _ = await repo.add_participant(
        session_id=session_id,
        display_name="Dave",
        provider="ollama",
        model="llama-3.1",
        model_tier="mid",
        model_family="llama",
        context_window=32000,
        auto_approve=False,
    )

    assert participant.role == "pending"


async def test_budget_values_stored_exactly(
    repo: ParticipantRepository,
    session_id: str,
    pool: asyncpg.Pool,
) -> None:
    """Budget values persist with exact precision."""
    participant, _ = await repo.add_participant(
        session_id=session_id,
        display_name="Eve",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        model_tier="high",
        model_family="claude",
        context_window=200000,
    )

    # Set budget via direct SQL (update not yet in repo scope)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET budget_daily = $1 WHERE id = $2",
            5.00,
            participant.id,
        )

    fetched = await repo.get_participant(participant.id)
    assert fetched is not None
    assert fetched.budget_daily == 5.00


async def test_list_participants_by_session(
    repo: ParticipantRepository,
    session_id: str,
) -> None:
    """list_participants returns all participants for a session."""
    await repo.add_participant(
        session_id=session_id,
        display_name="Frank",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
    )

    participants = await repo.list_participants(session_id)
    names = {p.display_name for p in participants}
    # Should include the facilitator plus Frank
    assert "Frank" in names


async def _add_haiku(
    repo: ParticipantRepository,
    session_id: str,
    *,
    name: str,
    api_key: str | None = None,
    auth_token: str | None = None,
):
    """Minimal helper to add a Haiku AI for reset/release tests."""
    return await repo.add_participant(
        session_id=session_id,
        display_name=name,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        model_tier="low",
        model_family="claude",
        context_window=200000,
        api_key=api_key,
        auth_token=auth_token,
        auto_approve=True,
    )


async def test_reset_ai_credentials_rotates_key(
    repo: ParticipantRepository,
    session_id: str,
) -> None:
    """reset_ai_credentials swaps the encrypted key and clears timeout/token state."""
    participant, _ = await _add_haiku(
        repo,
        session_id,
        name="RotateMe",
        api_key="sk-old-key-1111",
        auth_token="pre-reset-token",  # noqa: S106
    )
    old_encrypted = participant.api_key_encrypted
    new_key = "sk-new-key-9999"
    await repo.reset_ai_credentials(participant.id, api_key=new_key)

    refreshed = await repo.get_participant(participant.id)
    assert refreshed is not None
    assert refreshed.api_key_encrypted != old_encrypted
    fernet = Fernet(TEST_KEY.encode())
    assert fernet.decrypt(refreshed.api_key_encrypted.encode()).decode() == new_key
    assert refreshed.auth_token_hash is None
    assert refreshed.consecutive_timeouts == 0
    assert refreshed.status == "active"
    assert refreshed.provider == "anthropic"


async def test_reset_ai_credentials_optional_swap(
    repo: ParticipantRepository,
    session_id: str,
) -> None:
    """Passing provider/model/api_endpoint overrides them; None leaves as-is."""
    participant, _ = await _add_haiku(
        repo,
        session_id,
        name="SwapMe",
        api_key="sk-orig",
    )
    await repo.reset_ai_credentials(
        participant.id,
        api_key="sk-next",
        provider="openai",
        model="gpt-4o-mini",
        api_endpoint="https://api.openai.com",
    )
    refreshed = await repo.get_participant(participant.id)
    assert refreshed is not None
    assert refreshed.provider == "openai"
    assert refreshed.model == "gpt-4o-mini"
    assert refreshed.api_endpoint == "https://api.openai.com"


async def test_release_ai_slot_nulls_key_and_parks_status(
    repo: ParticipantRepository,
    session_id: str,
) -> None:
    """release_ai_slot sets status='reset' and nulls credentials."""
    participant, _ = await _add_haiku(
        repo,
        session_id,
        name="ReleaseMe",
        api_key="sk-to-release",
        auth_token="release-token",  # noqa: S106
    )
    await repo.release_ai_slot(participant.id)

    refreshed = await repo.get_participant(participant.id)
    assert refreshed is not None
    assert refreshed.api_key_encrypted is None
    assert refreshed.auth_token_hash is None
    assert refreshed.status == "reset"
