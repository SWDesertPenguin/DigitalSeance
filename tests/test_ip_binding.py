"""US8: Session IP binding tests."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.auth.service import AuthService
from src.repositories.errors import IPBindingMismatchError
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def session_with_token(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Create session + participant with token."""
    session_repo = SessionRepository(pool)
    session, _, _ = await session_repo.create_session(
        "IP Binding Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant, _ = await p_repo.add_participant(
        session_id=session.id,
        display_name="Bob",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auth_token="ip-test-token",  # noqa: S106
        auto_approve=True,
    )
    return session.id, participant.id, "ip-test-token"


@pytest.fixture
def auth(pool: asyncpg.Pool) -> AuthService:
    """Provide an AuthService."""
    return AuthService(pool, encryption_key=TEST_KEY)


async def test_first_auth_binds_ip(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """First authentication binds the client IP."""
    _, pid, token = session_with_token
    await auth.authenticate(token, "192.168.1.100")
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    p = await p_repo.get_participant(pid)
    assert p.bound_ip == "192.168.1.100"


async def test_same_ip_accepted(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
) -> None:
    """Subsequent auth from same IP succeeds."""
    _, _, token = session_with_token
    await auth.authenticate(token, "192.168.1.100")
    result = await auth.authenticate(token, "192.168.1.100")
    assert result is not None


async def test_different_ip_rejected(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
) -> None:
    """Auth from a different IP is rejected."""
    _, _, token = session_with_token
    await auth.authenticate(token, "192.168.1.100")
    with pytest.raises(IPBindingMismatchError):
        await auth.authenticate(token, "10.0.0.50")


async def test_rotation_clears_binding(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
) -> None:
    """Token rotation clears IP binding, allowing new IP."""
    _, pid, token = session_with_token
    await auth.authenticate(token, "192.168.1.100")
    new_token = await auth.rotate_token(pid)
    # New token should work from a different IP
    result = await auth.authenticate(new_token, "10.0.0.50")
    assert result.id == pid


async def test_concurrent_first_auth_one_ip_wins(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Audit M-01: concurrent first-auth from two IPs — exactly one wins.

    Pre-fix, both coroutines observed bound_ip=None on their in-memory
    Participant snapshot, both issued unconditional UPDATEs, and the
    second one silently overwrote the first. Now `_bind_ip` is atomic
    (UPDATE WHERE bound_ip IS NULL): exactly one rowcount=1 wins, the
    other reads the winner's IP, compares, and raises.
    """
    import asyncio

    _, pid, token = session_with_token

    results = await asyncio.gather(
        auth.authenticate(token, "192.168.1.100"),
        auth.authenticate(token, "10.0.0.50"),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, IPBindingMismatchError)]
    assert len(successes) == 1, (
        f"expected exactly one auth to succeed; got {len(successes)} "
        f"successes and {len(failures)} IPBindingMismatchError(s)"
    )
    assert len(failures) == 1, f"expected exactly one IPBindingMismatchError; got {len(failures)}"

    # Whichever IP won is whatever ends up persisted.
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    p = await p_repo.get_participant(pid)
    assert p.bound_ip in ("192.168.1.100", "10.0.0.50")
    assert p.bound_ip is not None
