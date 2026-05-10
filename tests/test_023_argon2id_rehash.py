# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 SC-007 transparent re-hash on parameter change (T041).

Seeds an account with a low-parameter argon2id hash, bumps the
``SACP_PASSWORD_ARGON2_TIME_COST`` env var, performs a successful
login, and asserts:

1. ``PasswordHasher.needs_rehash`` returns False against the post-login
   stored hash (the new hash matches current parameters).
2. The ``accounts.password_hash`` column actually changed.
3. The audit row carries ``rehash_performed: true``.

The transparent-rehash flow is the silent-upgrade path for password
parameter increases — operators tune the env var up over time and the
system re-hashes on each user's next login without forcing a full
reset.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import pytest

from src.accounts.hashing import PasswordHasher
from src.accounts.rate_limit import LoginRateLimiter
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
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")


def _build_app(pool: asyncpg.Pool, hasher: PasswordHasher) -> Any:
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
        rate_limiter=LoginRateLimiter(threshold=1000),
        hasher=hasher,
    )
    return app


async def _seed_low_param_account(
    pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
    email: str,
) -> tuple[str, str]:
    """Create + verify an account hashed under low argon2 parameters."""
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", "8192")
    app_low = _build_app(pool, PasswordHasher())
    service: AccountService = app_low.state.account_service
    create = await service.create_account(
        email=email,
        password="long-enough-pw-1",  # noqa: S106 -- test fixture
        client_ip="127.0.0.1",
    )
    plaintext = create.dev_plaintext_code
    assert plaintext is not None
    await service.verify_account(account_id=create.account_id, code=plaintext)
    async with pool.acquire() as conn:
        original_hash = await conn.fetchval(
            "SELECT password_hash FROM accounts WHERE id = $1",
            create.account_id,
        )
    return create.account_id, original_hash


async def _login_via_client(app: Any, email: str) -> int:
    async with asgi_client(app) as client:
        response = await client.post(
            "/tools/account/login",
            json={"email": email, "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    return response.status_code


async def _fetch_hash_and_login_audit(
    pool: asyncpg.Pool,
    account_id: str,
) -> tuple[str, dict]:
    async with pool.acquire() as conn:
        post_hash = await conn.fetchval(
            "SELECT password_hash FROM accounts WHERE id = $1",
            account_id,
        )
        row = await conn.fetchrow(
            "SELECT new_value FROM admin_audit_log "
            "WHERE target_id = $1 AND action = 'account_login' "
            "ORDER BY id DESC LIMIT 1",
            account_id,
        )
    return post_hash, json.loads(row["new_value"]) if row else {}


async def test_login_rehashes_when_parameters_change(
    pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bumping time_cost re-hashes the password on the next login."""
    account_id, original_hash = await _seed_low_param_account(
        pool, monkeypatch, "rehash@example.com"
    )
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "2")
    high_hasher = PasswordHasher()
    assert high_hasher.needs_rehash(original_hash)
    app_high = _build_app(pool, high_hasher)
    assert await _login_via_client(app_high, "rehash@example.com") == 200
    post_hash, _ = await _fetch_hash_and_login_audit(pool, account_id)
    assert post_hash != original_hash, "transparent re-hash did not update the column"
    assert not high_hasher.needs_rehash(post_hash)


async def test_login_audit_row_records_rehash_performed(
    pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The account_login audit row carries rehash_performed=true on a re-hash."""
    account_id, _ = await _seed_low_param_account(pool, monkeypatch, "audit-rehash@example.com")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "2")
    app_high = _build_app(pool, PasswordHasher())
    assert await _login_via_client(app_high, "audit-rehash@example.com") == 200
    _, payload = await _fetch_hash_and_login_audit(pool, account_id)
    assert payload.get("rehash_performed") is True


async def test_login_does_not_rehash_when_params_unchanged(
    pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No re-hash when current parameters match the stored hash's."""
    account_id, original_hash = await _seed_low_param_account(
        pool, monkeypatch, "stable@example.com"
    )
    app = _build_app(pool, PasswordHasher())
    assert await _login_via_client(app, "stable@example.com") == 200
    post_hash, payload = await _fetch_hash_and_login_audit(pool, account_id)
    assert post_hash == original_hash
    assert payload.get("rehash_performed") is False
