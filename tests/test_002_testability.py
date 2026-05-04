"""002 participant-auth testability suite (Phase B audit fix).

Covers:
  - Token expiry (FR-002, FR-012, FR-013)
  - Token format (FR-A1)
  - IP binding (FR-016, FR-017, FR-018)
  - TRUST_PROXY (FR-023)
  - Facilitator transfer atomicity + audit (FR-011, FR-014)
  - All-actions audit-log coverage (FR-014)
  - Brute-force gap documented absence (FR-024)
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.auth.service import AuthService
from src.mcp_server.middleware import _get_client_ip
from src.repositories.errors import (
    IPBindingMismatchError,
    NotFacilitatorError,
    TokenExpiredError,
    TokenInvalidError,
)
from src.repositories.log_repo import LogRepository
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def session_with_token(
    pool: asyncpg.Pool,
) -> tuple[str, str, str, str]:
    """Create session + approved participant. Returns (sid, fid, pid, token)."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Auth Test 002",
        facilitator_display_name="Facilitator",
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
        auth_token="test-token-002",  # noqa: S106
        auto_approve=True,
    )
    return session.id, facilitator.id, participant.id, "test-token-002"


@pytest.fixture
def auth(pool: asyncpg.Pool) -> AuthService:
    return AuthService(pool, encryption_key=TEST_KEY)


@pytest.fixture
def p_repo(pool: asyncpg.Pool) -> ParticipantRepository:
    return ParticipantRepository(pool, encryption_key=TEST_KEY)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _make_session(pool: asyncpg.Pool) -> tuple[str, str]:
    """Create a bare session. Returns (session_id, facilitator_id)."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Test Session",
        facilitator_display_name="Facilitator",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, facilitator.id


async def _add_p(
    p_repo: ParticipantRepository,
    session_id: str,
    *,
    auto_approve: bool,
    token: str | None = None,
):
    """Add a minimal participant. Returns the Participant record."""
    p, _ = await p_repo.add_participant(
        session_id=session_id,
        display_name="P",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auto_approve=auto_approve,
        auth_token=token,
    )
    return p


async def _create_transfer_session(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Create session with facilitator + approved participant. Returns (sid, fid, new_fid)."""
    sid, fid = await _make_session(pool)
    pr = ParticipantRepository(pool, encryption_key=TEST_KEY)
    target = await _add_p(pr, sid, auto_approve=True)
    return sid, fid, target.id


def _mock_request(client_host: str, xff: str | None = None) -> SimpleNamespace:
    headers: dict[str, str] = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(
        client=SimpleNamespace(host=client_host),
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Token expiry (FR-002, FR-012, FR-013)
# ---------------------------------------------------------------------------


async def test_expired_token_rejected(
    auth: AuthService,
    session_with_token: tuple[str, str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Expired token raises TokenExpiredError (FR-002)."""
    _, _, pid, token = session_with_token
    past = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(hours=1)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET token_expires_at = $1 WHERE id = $2",
            past,
            pid,
        )
    with pytest.raises(TokenExpiredError):
        await auth.authenticate(token, "127.0.0.1")


async def test_valid_before_expiry_accepted(
    auth: AuthService,
    session_with_token: tuple[str, str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Token with future expiry authenticates normally (FR-002)."""
    _, _, pid, token = session_with_token
    future = datetime.now(tz=UTC).replace(tzinfo=None) + timedelta(days=7)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET token_expires_at = $1 WHERE id = $2",
            future,
            pid,
        )
    result = await auth.authenticate(token, "127.0.0.1")
    assert result.id == pid


async def test_rotation_resets_expiry(
    auth: AuthService,
    session_with_token: tuple[str, str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Token rotation sets token_expires_at to a future timestamp (FR-013)."""
    _, _, pid, _ = session_with_token
    await auth.rotate_token(pid)
    async with pool.acquire() as conn:
        expires = await conn.fetchval(
            "SELECT token_expires_at FROM participants WHERE id = $1",
            pid,
        )
    assert expires is not None
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    assert expires > now


# ---------------------------------------------------------------------------
# Token format (FR-A1)
# ---------------------------------------------------------------------------


async def test_token_format_is_url_safe(
    auth: AuthService,
    session_with_token: tuple[str, str, str, str],
) -> None:
    """Rotated token is URL-safe base64 with sufficient entropy (FR-A1)."""
    _, _, pid, _ = session_with_token
    token = await auth.rotate_token(pid)
    assert re.fullmatch(r"[A-Za-z0-9_\-]+", token)
    assert len(token) >= 40


# ---------------------------------------------------------------------------
# IP binding (FR-016, FR-017, FR-018)
# ---------------------------------------------------------------------------


async def test_first_auth_binds_ip(
    auth: AuthService,
    session_with_token: tuple[str, str, str, str],
    p_repo: ParticipantRepository,
) -> None:
    """First authentication atomically binds the client IP (FR-016)."""
    _, _, pid, token = session_with_token
    await auth.authenticate(token, "10.0.0.1")
    participant = await p_repo.get_participant(pid)
    assert participant.bound_ip == "10.0.0.1"


async def test_same_ip_accepted_after_bind(
    auth: AuthService,
    session_with_token: tuple[str, str, str, str],
) -> None:
    """Subsequent requests from the same IP succeed (FR-016)."""
    _, _, pid, token = session_with_token
    await auth.authenticate(token, "10.0.0.1")
    result = await auth.authenticate(token, "10.0.0.1")
    assert result.id == pid


async def test_different_ip_rejected_after_bind(
    auth: AuthService,
    session_with_token: tuple[str, str, str, str],
) -> None:
    """Request from a different IP after binding raises IPBindingMismatchError (FR-017)."""
    _, _, _, token = session_with_token
    await auth.authenticate(token, "10.0.0.1")
    with pytest.raises(IPBindingMismatchError):
        await auth.authenticate(token, "10.0.0.2")


async def test_rotation_resets_ip_binding(
    auth: AuthService,
    session_with_token: tuple[str, str, str, str],
    p_repo: ParticipantRepository,
) -> None:
    """Token rotation clears bound_ip; new token re-binds to a new IP (FR-018)."""
    _, _, pid, old_token = session_with_token
    await auth.authenticate(old_token, "10.0.0.1")
    new_token = await auth.rotate_token(pid)
    result = await auth.authenticate(new_token, "10.0.0.2")
    assert result.id == pid
    participant = await p_repo.get_participant(pid)
    assert participant.bound_ip == "10.0.0.2"


# ---------------------------------------------------------------------------
# TRUST_PROXY (FR-023) — unit tests against _get_client_ip directly
# ---------------------------------------------------------------------------


def test_trust_proxy_off_ignores_xff(monkeypatch: pytest.MonkeyPatch) -> None:
    """SACP_TRUST_PROXY=0 uses direct client.host and ignores XFF (FR-023)."""
    monkeypatch.setenv("SACP_TRUST_PROXY", "0")
    req = _mock_request("1.2.3.4", xff="9.9.9.9")
    assert _get_client_ip(req) == "1.2.3.4"


def test_trust_proxy_on_uses_rightmost_xff(monkeypatch: pytest.MonkeyPatch) -> None:
    """SACP_TRUST_PROXY=1 takes the rightmost X-Forwarded-For entry (FR-023)."""
    monkeypatch.setenv("SACP_TRUST_PROXY", "1")
    req = _mock_request("proxy.internal", xff="1.2.3.4, 5.6.7.8")
    assert _get_client_ip(req) == "5.6.7.8"


def test_loopback_caller_trusts_xff_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loopback hop is the in-container Web UI proxy; honor its XFF.

    Pre-fix the same-origin proxy (audit H-02) forwarded MCP calls from
    `127.0.0.1` and the IP-binding check 403'd against the bound browser
    IP. Loopback callers are by definition on-host, so honoring their
    XFF doesn't weaken the off-host threat model IP binding defends.
    """
    monkeypatch.delenv("SACP_TRUST_PROXY", raising=False)
    req = _mock_request("127.0.0.1", xff="192.168.86.213")
    assert _get_client_ip(req) == "192.168.86.213"


def test_loopback_ipv6_caller_also_trusts_xff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IPv6 loopback `::1` is treated the same as `127.0.0.1`."""
    monkeypatch.delenv("SACP_TRUST_PROXY", raising=False)
    req = _mock_request("::1", xff="192.168.86.213")
    assert _get_client_ip(req) == "192.168.86.213"


def test_loopback_caller_without_xff_falls_back_to_direct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loopback hop without XFF still returns loopback (no spoof avenue)."""
    monkeypatch.delenv("SACP_TRUST_PROXY", raising=False)
    req = _mock_request("127.0.0.1")
    assert _get_client_ip(req) == "127.0.0.1"


def test_non_loopback_xff_ignored_when_trust_proxy_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Off-host caller with XFF still gets the direct IP without TRUST_PROXY."""
    monkeypatch.delenv("SACP_TRUST_PROXY", raising=False)
    req = _mock_request("203.0.113.5", xff="198.51.100.7")
    assert _get_client_ip(req) == "203.0.113.5"


# ---------------------------------------------------------------------------
# Facilitator transfer (FR-011, FR-014)
# ---------------------------------------------------------------------------


async def test_transfer_swaps_roles(
    auth: AuthService,
    pool: asyncpg.Pool,
    p_repo: ParticipantRepository,
) -> None:
    """Transfer demotes old facilitator to participant and promotes target (FR-011)."""
    sid, fid, new_fid = await _create_transfer_session(pool)
    await auth.transfer_facilitator(
        facilitator_id=fid,
        session_id=sid,
        target_id=new_fid,
    )
    old = await p_repo.get_participant(fid)
    new = await p_repo.get_participant(new_fid)
    assert old.role == "participant"
    assert new.role == "facilitator"


async def test_transfer_updates_session_facilitator_id(
    auth: AuthService,
    pool: asyncpg.Pool,
) -> None:
    """Transfer updates sessions.facilitator_id to the new facilitator (FR-011)."""
    sid, fid, new_fid = await _create_transfer_session(pool)
    await auth.transfer_facilitator(
        facilitator_id=fid,
        session_id=sid,
        target_id=new_fid,
    )
    async with pool.acquire() as conn:
        current_fid = await conn.fetchval(
            "SELECT facilitator_id FROM sessions WHERE id = $1",
            sid,
        )
    assert current_fid == new_fid


async def test_transfer_logged(
    auth: AuthService,
    pool: asyncpg.Pool,
) -> None:
    """Facilitator transfer is recorded in admin_audit_log (FR-014)."""
    sid, fid, new_fid = await _create_transfer_session(pool)
    await auth.transfer_facilitator(
        facilitator_id=fid,
        session_id=sid,
        target_id=new_fid,
    )
    log_repo = LogRepository(pool)
    entries = await log_repo.get_audit_log(sid)
    assert "transfer_facilitator" in [e.action for e in entries]


async def test_transfer_to_pending_rejected(
    auth: AuthService,
    pool: asyncpg.Pool,
) -> None:
    """Transfer to a pending participant is rejected — target must be active (FR-011)."""
    sid, fid, _ = await _create_transfer_session(pool)
    pr = ParticipantRepository(pool, encryption_key=TEST_KEY)
    pending = await _add_p(pr, sid, auto_approve=False)
    with pytest.raises(ValueError, match="participant"):
        await auth.transfer_facilitator(
            facilitator_id=fid,
            session_id=sid,
            target_id=pending.id,
        )


async def test_non_facilitator_cannot_transfer(
    auth: AuthService,
    pool: asyncpg.Pool,
) -> None:
    """Non-facilitator attempting transfer raises NotFacilitatorError (FR-010)."""
    sid, fid, new_fid = await _create_transfer_session(pool)
    with pytest.raises(NotFacilitatorError):
        await auth.transfer_facilitator(
            facilitator_id=new_fid,
            session_id=sid,
            target_id=fid,
        )


# ---------------------------------------------------------------------------
# Audit log completeness (FR-014) — all five facilitator actions
# ---------------------------------------------------------------------------


async def test_all_facilitator_actions_logged(
    auth: AuthService,
    pool: asyncpg.Pool,
) -> None:
    """All five facilitator-initiated actions appear in admin_audit_log (FR-014)."""
    sid, fid = await _make_session(pool)
    pr = ParticipantRepository(pool, encryption_key=TEST_KEY)
    p1 = await _add_p(pr, sid, auto_approve=False)
    await auth.approve_participant(facilitator_id=fid, session_id=sid, participant_id=p1.id)
    p2 = await _add_p(pr, sid, auto_approve=False)
    await auth.reject_participant(facilitator_id=fid, session_id=sid, participant_id=p2.id)
    p3 = await _add_p(pr, sid, auto_approve=True)
    await auth.remove_participant(facilitator_id=fid, session_id=sid, participant_id=p3.id)
    p4 = await _add_p(pr, sid, auto_approve=True, token="rev-tok")  # noqa: S106
    await auth.revoke_token(facilitator_id=fid, session_id=sid, participant_id=p4.id)
    p5 = await _add_p(pr, sid, auto_approve=True)
    await auth.transfer_facilitator(facilitator_id=fid, session_id=sid, target_id=p5.id)
    entries = await LogRepository(pool).get_audit_log(sid)
    actions = {e.action for e in entries}
    expected = {
        "approve_participant",
        "reject_participant",
        "remove_participant",
        "revoke_token",
        "transfer_facilitator",
    }
    assert expected <= actions


# ---------------------------------------------------------------------------
# Brute-force gap documented absence (FR-024)
# ---------------------------------------------------------------------------


async def test_brute_force_gap_is_real(
    auth: AuthService,
    session_with_token: tuple[str, str, str, str],
) -> None:
    """Five consecutive wrong tokens do not lock out the valid token (FR-024 OOS).

    FR-024 explicitly defers brute-force protection to Phase 3. This test
    documents the gap: wrong tokens fail individually but do not trigger any
    account lockout, so the valid token still authenticates afterwards.
    """
    _, _, pid, valid_token = session_with_token
    for _ in range(5):
        with pytest.raises(TokenInvalidError):
            await auth.authenticate("wrong-token", "127.0.0.1")
    result = await auth.authenticate(valid_token, "127.0.0.1")
    assert result.id == pid
