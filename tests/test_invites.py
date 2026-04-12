"""US8: Invitations — hash storage, use limits, and expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from src.repositories.errors import InviteExhaustedError, InviteExpiredError
from src.repositories.invite_repo import InviteRepository
from src.repositories.session_repo import SessionRepository


@pytest.fixture
async def session_and_facilitator(
    pool: asyncpg.Pool,
) -> tuple[str, str]:
    """Create a session and return (session_id, facilitator_id)."""
    repo = SessionRepository(pool)
    session, participant, _ = await repo.create_session(
        "Invite Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, participant.id


@pytest.fixture
def repo(pool: asyncpg.Pool) -> InviteRepository:
    """Provide an InviteRepository."""
    return InviteRepository(pool)


async def test_token_stored_as_hash(
    repo: InviteRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Plaintext token is not stored in the database."""
    sid, pid = session_and_facilitator
    invite, plaintext = await repo.create_invite(
        session_id=sid,
        created_by=pid,
    )
    assert invite.token_hash != plaintext
    assert len(invite.token_hash) == 64  # SHA-256 hex


async def test_redeem_increments_use_count(
    repo: InviteRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Redeeming an invite increments uses."""
    sid, pid = session_and_facilitator
    _, plaintext = await repo.create_invite(
        session_id=sid,
        created_by=pid,
        max_uses=5,
    )
    redeemed = await repo.redeem_invite(plaintext)
    assert redeemed.uses == 1


async def test_single_use_rejected_on_second(
    repo: InviteRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Single-use invite rejected on second redemption."""
    sid, pid = session_and_facilitator
    _, plaintext = await repo.create_invite(
        session_id=sid,
        created_by=pid,
        max_uses=1,
    )
    await repo.redeem_invite(plaintext)
    with pytest.raises(InviteExhaustedError):
        await repo.redeem_invite(plaintext)


async def test_expired_invite_rejected(
    repo: InviteRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Expired invites are rejected."""
    sid, pid = session_and_facilitator
    past = datetime.now(tz=UTC) - timedelta(hours=1)
    _, plaintext = await repo.create_invite(
        session_id=sid,
        created_by=pid,
        expires_at=past,
    )
    with pytest.raises(InviteExpiredError):
        await repo.redeem_invite(plaintext)


async def test_multi_use_works_up_to_max(
    repo: InviteRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Multi-use invite works up to max_uses then rejects."""
    sid, pid = session_and_facilitator
    _, plaintext = await repo.create_invite(
        session_id=sid,
        created_by=pid,
        max_uses=2,
    )
    await repo.redeem_invite(plaintext)
    await repo.redeem_invite(plaintext)
    with pytest.raises(InviteExhaustedError):
        await repo.redeem_invite(plaintext)
