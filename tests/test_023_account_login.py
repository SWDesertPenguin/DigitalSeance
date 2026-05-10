# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 US1 acceptance scenarios 4-5 — login + 401 (T038).

Drives ``POST /tools/account/login`` after a successful create + verify.
Asserts:

- Scenario 4: login success returns 200 + sets a signed session cookie
  + writes an ``account_login`` audit row.
- Scenario 5: login failure returns a generic ``invalid_credentials``
  401 — the response body MUST NOT distinguish "non-existent email"
  from "wrong password" or "deleted account" (FR-014 spirit + clarify
  Q11 + spec.md US1 scenario 5).
"""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest

from src.accounts.service import AccountService
from src.repositories.account_repo import AccountRepository
from src.repositories.log_repo import LogRepository
from src.web_ui.app import create_web_app
from src.web_ui.auth import COOKIE_NAME
from src.web_ui.security import CSRF_HEADER, CSRF_VALUE
from src.web_ui.session_store import SessionStore
from tests.conftest import asgi_client

_CSRF = {CSRF_HEADER: CSRF_VALUE}


@pytest.fixture(autouse=True)
def _accounts_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")
    # Cap argon2id cost for fast CI runs.
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", "8192")


@pytest.fixture
async def app_and_service(pool: asyncpg.Pool) -> Any:
    """Build the app + AccountService + helper to seed verified accounts."""
    app = create_web_app()
    app.state.pool = pool
    log_repo = LogRepository(pool)
    session_store = SessionStore()
    app.state.log_repo = log_repo
    app.state.session_store = session_store
    service = AccountService(
        account_repo=AccountRepository(pool),
        log_repo=log_repo,
        session_store=session_store,
    )
    app.state.account_service = service
    return app, service


async def _seed_active(service: AccountService, email: str, password: str) -> str:
    """Create + verify an account; return the account_id in active status."""
    create = await service.create_account(
        email=email,
        password=password,
        client_ip="127.0.0.1",
    )
    plaintext = create.dev_plaintext_code
    assert plaintext is not None
    await service.verify_account(account_id=create.account_id, code=plaintext)
    return create.account_id


# ---------------------------------------------------------------------------
# Scenario 4 — login success (cookie + audit)
# ---------------------------------------------------------------------------


async def test_login_success_returns_cookie_and_audit_row(
    app_and_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """200 + Set-Cookie + account_login audit row."""
    app, service = app_and_service
    account_id = await _seed_active(service, "ok@example.com", "long-enough-pw-1")

    async with asgi_client(app) as client:
        response = await client.post(
            "/tools/account/login",
            json={"email": "ok@example.com", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["account_id"] == account_id
    assert body["expires_in"] > 0
    assert COOKIE_NAME in response.cookies

    async with pool.acquire() as conn:
        login_rows = await conn.fetch(
            "SELECT * FROM admin_audit_log " "WHERE target_id = $1 AND action = 'account_login'",
            account_id,
        )
    assert len(login_rows) == 1


async def test_login_success_case_insensitive_email(
    app_and_service: Any,
) -> None:
    """Login accepts uppercase/mixed-case email (research §2 canonicalization)."""
    app, service = app_and_service
    await _seed_active(service, "case@example.com", "long-enough-pw-1")

    async with asgi_client(app) as client:
        response = await client.post(
            "/tools/account/login",
            json={"email": "CASE@Example.COM", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    assert response.status_code == 200


async def test_login_success_updates_last_login_at(
    app_and_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """A successful login stamps accounts.last_login_at."""
    app, service = app_and_service
    account_id = await _seed_active(service, "stamp@example.com", "long-enough-pw-1")

    async with asgi_client(app) as client:
        response = await client.post(
            "/tools/account/login",
            json={"email": "stamp@example.com", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    assert response.status_code == 200

    async with pool.acquire() as conn:
        last_login = await conn.fetchval(
            "SELECT last_login_at FROM accounts WHERE id = $1",
            account_id,
        )
    assert last_login is not None


# ---------------------------------------------------------------------------
# Scenario 5 — generic 401 + no info leak
# ---------------------------------------------------------------------------


async def test_login_unknown_email_returns_generic_401(
    app_and_service: Any,
) -> None:
    """Email never registered: 401 + invalid_credentials, no info leak."""
    app, _ = app_and_service
    async with asgi_client(app) as client:
        response = await client.post(
            "/tools/account/login",
            json={"email": "ghost@example.com", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"
    assert COOKIE_NAME not in response.cookies


async def test_login_wrong_password_returns_generic_401(
    app_and_service: Any,
) -> None:
    """Email exists, password wrong: same 401 + invalid_credentials."""
    app, service = app_and_service
    await _seed_active(service, "wrong@example.com", "correct-password-12")

    async with asgi_client(app) as client:
        response = await client.post(
            "/tools/account/login",
            json={"email": "wrong@example.com", "password": "wrong-password-99"},
            headers=_CSRF,
        )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


async def test_login_pending_verification_returns_generic_401(
    app_and_service: Any,
) -> None:
    """Account exists in pending_verification: same 401 (no leak)."""
    app, service = app_and_service
    await service.create_account(
        email="pending@example.com",
        password="long-enough-pw-1",  # noqa: S106 — test fixture
        client_ip="127.0.0.1",
    )
    # Skip the verify; account stays pending_verification.
    async with asgi_client(app) as client:
        response = await client.post(
            "/tools/account/login",
            json={"email": "pending@example.com", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


async def test_login_deleted_account_returns_generic_401(
    app_and_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """Deleted account: same 401 (no info leak about deletion status)."""
    app, service = app_and_service
    account_id = await _seed_active(service, "deleted-login@example.com", "long-enough-pw-1")
    repo = AccountRepository(pool)
    await repo.mark_account_deleted(account_id)

    async with asgi_client(app) as client:
        response = await client.post(
            "/tools/account/login",
            json={
                "email": "deleted-login@example.com",
                "password": "long-enough-pw-1",
            },
            headers=_CSRF,
        )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


async def test_login_failed_emits_audit_row(
    app_and_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """Each failure path writes an account_login_failed audit row."""
    app, _ = app_and_service
    async with asgi_client(app) as client:
        await client.post(
            "/tools/account/login",
            json={"email": "fail@example.com", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT action, new_value FROM admin_audit_log "
            "WHERE action = 'account_login_failed'",
        )
    assert len(rows) == 1
    assert "elapsed_ms" in rows[0]["new_value"]
    assert "failure_reason" in rows[0]["new_value"]


async def test_login_response_body_is_identical_across_failure_modes(
    app_and_service: Any,
) -> None:
    """SC-005 contract — the body MUST NOT vary between failure modes."""
    app, service = app_and_service
    await _seed_active(service, "diff@example.com", "correct-password-12")
    async with asgi_client(app) as client:
        ghost = await client.post(
            "/tools/account/login",
            json={"email": "ghost-x@example.com", "password": "any-pw-here-12"},
            headers=_CSRF,
        )
        wrong = await client.post(
            "/tools/account/login",
            json={"email": "diff@example.com", "password": "wrong-pw-here-99"},
            headers=_CSRF,
        )
    assert ghost.status_code == wrong.status_code == 401
    assert ghost.json() == wrong.json()
