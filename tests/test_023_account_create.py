# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 US1 acceptance scenarios 1-3 — create + verify (T037).

Drives the ``POST /tools/account/create`` endpoint and the matching
verification flow. Uses the real Postgres pool (skipped without one)
plus the in-process noop email transport so the verification code
surfaces via the audit log without a real SMTP hop.

Coverage map (per spec.md US1):

- Scenario 1: account creation persists ``status='pending_verification'``
  with an argon2id-hashed password (NOT plaintext).
- Scenario 2: a 16-char base32 verification code is emitted via the
  configured transport AND an ``account_verification_emitted`` audit
  row is written carrying the HMAC hash of the code.
- Scenario 3: code submission flips ``status`` to ``active`` and writes
  the ``account_verification_consumed`` audit row; an incorrect or
  expired code returns 400.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest

from src.accounts.codes import hash_code
from src.accounts.service import AccountService
from src.repositories.account_repo import AccountRepository
from src.repositories.log_repo import LogRepository
from src.web_ui.app import create_web_app
from src.web_ui.security import CSRF_HEADER, CSRF_VALUE
from src.web_ui.session_store import SessionStore
from tests.conftest import asgi_client

_CSRF = {CSRF_HEADER: CSRF_VALUE}


@pytest.fixture(autouse=True)
def _accounts_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable the master switch + insecure cookies for TestClient (HTTP)."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")
    # Keep argon2id parameters at the test floor so account creation
    # stays under a few hundred ms in CI without sacrificing the
    # parameter-shape coverage.
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", "8192")


@pytest.fixture
async def app_with_accounts(pool: asyncpg.Pool) -> Any:
    """Build the Web UI app with a wired AccountService backed by ``pool``."""
    app = create_web_app()
    app.state.pool = pool
    log_repo = LogRepository(pool)
    session_store = SessionStore()
    app.state.log_repo = log_repo
    app.state.session_store = session_store
    app.state.account_service = AccountService(
        account_repo=AccountRepository(pool),
        log_repo=log_repo,
        session_store=session_store,
    )
    return app


# ---------------------------------------------------------------------------
# Scenario 1 — account creation persists pending_verification + argon2id hash
# ---------------------------------------------------------------------------


async def test_create_account_persists_pending_verification(
    app_with_accounts: Any,
    pool: asyncpg.Pool,
) -> None:
    """201 + status='pending_verification' + argon2id-hashed password."""
    async with asgi_client(app_with_accounts) as client:
        response = await client.post(
            "/tools/account/create",
            json={"email": "user1@example.com", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending_verification"
    assert body["verification_email_sent"] is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT email, password_hash, status FROM accounts WHERE id = $1",
            body["account_id"],
        )
    assert row is not None
    assert row["email"] == "user1@example.com"
    assert row["status"] == "pending_verification"
    # The persisted hash MUST be the argon2id-encoded form, NOT the plaintext.
    assert row["password_hash"].startswith("$argon2id$")
    assert "long-enough-pw-1" not in row["password_hash"]


async def test_create_account_rejects_invalid_email(app_with_accounts: Any) -> None:
    """422 + email_invalid for a syntactically broken address."""
    async with asgi_client(app_with_accounts) as client:
        response = await client.post(
            "/tools/account/create",
            json={"email": "not-an-email", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "email_invalid"


async def test_create_account_rejects_short_password(app_with_accounts: Any) -> None:
    """422 + password_too_short below the 12-char floor."""
    async with asgi_client(app_with_accounts) as client:
        response = await client.post(
            "/tools/account/create",
            json={"email": "user2@example.com", "password": "short"},
            headers=_CSRF,
        )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "password_too_short"


async def test_create_account_rejects_duplicate_active_email(
    app_with_accounts: Any,
) -> None:
    """409 + registration_failed on a colliding pending/active email."""
    async with asgi_client(app_with_accounts) as client:
        first = await client.post(
            "/tools/account/create",
            json={"email": "dup@example.com", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
        assert first.status_code == 201
        second = await client.post(
            "/tools/account/create",
            json={"email": "dup@example.com", "password": "another-long-pw-2"},
            headers=_CSRF,
        )
    assert second.status_code == 409
    assert second.json()["detail"]["error"] == "registration_failed"


# ---------------------------------------------------------------------------
# Scenario 2 — verification code emission + audit row
# ---------------------------------------------------------------------------


async def test_create_account_emits_verification_audit_row(
    app_with_accounts: Any,
    pool: asyncpg.Pool,
) -> None:
    """A successful create writes account_create + account_verification_emitted."""
    async with asgi_client(app_with_accounts) as client:
        response = await client.post(
            "/tools/account/create",
            json={"email": "audit@example.com", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    assert response.status_code == 201
    account_id = response.json()["account_id"]

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT action, target_id, new_value FROM admin_audit_log "
            "WHERE target_id = $1 ORDER BY id ASC",
            account_id,
        )
    actions = [r["action"] for r in rows]
    assert "account_create" in actions
    assert "account_verification_emitted" in actions
    # The emit row must carry a code_hash (the HMAC of the plaintext)
    # so the consume path can look it up by hash without storing the
    # plaintext.
    emit_row = next(r for r in rows if r["action"] == "account_verification_emitted")
    assert "code_hash" in emit_row["new_value"]


# ---------------------------------------------------------------------------
# Scenario 3 — verification consumes the code and flips status
# ---------------------------------------------------------------------------


async def _assert_account_active_with_consumed_row(*, pool: asyncpg.Pool, account_id: str) -> None:
    """Cross-check that the account row + consumed audit row landed."""
    async with pool.acquire() as conn:
        status_row = await conn.fetchval("SELECT status FROM accounts WHERE id = $1", account_id)
        consumed_actions = await conn.fetch(
            "SELECT action FROM admin_audit_log WHERE target_id = $1 "
            "AND action = 'account_verification_consumed'",
            account_id,
        )
    assert status_row == "active"
    assert len(consumed_actions) == 1


async def test_verify_account_flips_status_to_active(
    app_with_accounts: Any,
    pool: asyncpg.Pool,
) -> None:
    """Submitting the correct code flips status to active + writes consumed."""
    service: AccountService = app_with_accounts.state.account_service
    create = await service.create_account(
        email="verify@example.com",
        password="long-enough-pw-1",  # noqa: S106 -- test fixture
        client_ip="127.0.0.1",
    )
    plaintext = create.dev_plaintext_code
    assert plaintext is not None, "noop transport must surface the plaintext"
    async with asgi_client(app_with_accounts) as client:
        response = await client.post(
            "/tools/account/verify",
            json={"account_id": create.account_id, "code": plaintext},
            headers=_CSRF,
        )
    assert response.status_code == 200, response.text
    assert response.json() == {"account_id": create.account_id, "status": "active"}
    await _assert_account_active_with_consumed_row(pool=pool, account_id=create.account_id)


async def test_verify_account_rejects_wrong_code(
    app_with_accounts: Any,
) -> None:
    """An incorrect 16-char code returns 400 + invalid_or_expired_code."""
    service: AccountService = app_with_accounts.state.account_service
    create = await service.create_account(
        email="wrong@example.com",
        password="long-enough-pw-1",  # noqa: S106 — test fixture
        client_ip="127.0.0.1",
    )
    async with asgi_client(app_with_accounts) as client:
        response = await client.post(
            "/tools/account/verify",
            json={"account_id": create.account_id, "code": "AAAAAAAAAAAAAAAA"},
            headers=_CSRF,
        )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_or_expired_code"


async def test_verify_account_rejects_short_code(
    app_with_accounts: Any,
) -> None:
    """A code with the wrong length is rejected before any lookup."""
    service: AccountService = app_with_accounts.state.account_service
    create = await service.create_account(
        email="short-code@example.com",
        password="long-enough-pw-1",  # noqa: S106 — test fixture
        client_ip="127.0.0.1",
    )
    async with asgi_client(app_with_accounts) as client:
        response = await client.post(
            "/tools/account/verify",
            json={"account_id": create.account_id, "code": "ABC"},
            headers=_CSRF,
        )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_or_expired_code"


async def test_verify_account_idempotent_not_replayable(
    app_with_accounts: Any,
) -> None:
    """A consumed code cannot be re-used for a second verify."""
    service: AccountService = app_with_accounts.state.account_service
    create = await service.create_account(
        email="replay@example.com",
        password="long-enough-pw-1",  # noqa: S106 — test fixture
        client_ip="127.0.0.1",
    )
    plaintext = create.dev_plaintext_code
    assert plaintext is not None
    async with asgi_client(app_with_accounts) as client:
        first = await client.post(
            "/tools/account/verify",
            json={"account_id": create.account_id, "code": plaintext},
            headers=_CSRF,
        )
        assert first.status_code == 200
        second = await client.post(
            "/tools/account/verify",
            json={"account_id": create.account_id, "code": plaintext},
            headers=_CSRF,
        )
    # Second call must NOT flip a non-pending account back to active;
    # the get_account_by_id branch already requires pending_verification
    # status, so 400 is the contract.
    assert second.status_code == 400
    assert second.json()["detail"]["error"] == "invalid_or_expired_code"


# ---------------------------------------------------------------------------
# Cross-check: the persisted code_hash matches hash_code(plaintext)
# ---------------------------------------------------------------------------


async def test_verification_code_hash_matches_hmac_lookup(
    app_with_accounts: Any,
    pool: asyncpg.Pool,
) -> None:
    """The audit-row code_hash is the HMAC of the plaintext (research §3)."""
    service: AccountService = app_with_accounts.state.account_service
    create = await service.create_account(
        email="hmac@example.com",
        password="long-enough-pw-1",  # noqa: S106 — test fixture
        client_ip="127.0.0.1",
    )
    expected_hash = hash_code(create.dev_plaintext_code or "")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT new_value FROM admin_audit_log "
            "WHERE target_id = $1 AND action = 'account_verification_emitted'",
            create.account_id,
        )
    assert row is not None
    assert expected_hash in row["new_value"]
