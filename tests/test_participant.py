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
