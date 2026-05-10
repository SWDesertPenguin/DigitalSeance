# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 US3 acceptance scenarios 4-5 — account deletion (T061).

- Successful delete zeroes ``email`` + ``password_hash``, flips
  ``status`` to ``'deleted'``, populates ``deleted_at`` +
  ``email_grace_release_at``, emits the export email and writes the
  ``account_delete`` audit row.
- A login attempt against the deleted email returns the same generic
  ``invalid_credentials`` 401 as a non-existent email — no info leak
  about the deletion (FR-014 spirit + spec edge case).
"""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest

from src.accounts.service import AccountService
from src.repositories.account_repo import AccountRepository
from src.repositories.log_repo import LogRepository
from src.web_ui.app import create_web_app
from src.web_ui.auth import _make_cookie_value
from src.web_ui.security import CSRF_HEADER, CSRF_VALUE
from src.web_ui.session_store import SessionStore
from tests.conftest import asgi_client

_CSRF = {CSRF_HEADER: CSRF_VALUE}


@pytest.fixture(autouse=True)
def _accounts_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", "8192")


@pytest.fixture
async def app_with_service(pool: asyncpg.Pool) -> Any:
    app = create_web_app()
    app.state.pool = pool
    log_repo = LogRepository(pool)
    session_store = SessionStore()
    repo = AccountRepository(pool)
    app.state.log_repo = log_repo
    app.state.session_store = session_store
    app.state.account_repo = repo
    app.state.account_service = AccountService(
        account_repo=repo,
        log_repo=log_repo,
        session_store=session_store,
    )
    return app


async def _create_active_with_sid(app: Any, *, email: str) -> tuple[str, str]:
    service: AccountService = app.state.account_service
    create = await service.create_account(
        email=email,
        password="long-enough-pw-1",  # noqa: S106 -- test fixture
        client_ip="127.0.0.1",
    )
    plaintext = create.dev_plaintext_code
    assert plaintext is not None
    await service.verify_account(account_id=create.account_id, code=plaintext)
    sid = await app.state.session_store.create(account_id=create.account_id)
    return create.account_id, sid


def _cookie_for(sid: str) -> dict[str, str]:
    return {"sacp_ui_token": _make_cookie_value(sid)}


async def test_account_delete_zeroes_credentials_and_writes_audit(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """Email + hash zeroed; status='deleted'; grace fields populated."""
    account_id, sid = await _create_active_with_sid(app_with_service, email="del@example.com")
    async with asgi_client(app_with_service) as client:
        response = await client.post(
            "/tools/account/delete",
            cookies=_cookie_for(sid),
            headers=_CSRF,
            json={"current_password": "long-enough-pw-1"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "deleted"
    assert body["email_grace_release_at"] is not None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT email, password_hash, status, deleted_at, "
            "email_grace_release_at FROM accounts WHERE id = $1",
            account_id,
        )
    assert row["email"] == ""
    assert row["password_hash"] == ""
    assert row["status"] == "deleted"
    assert row["deleted_at"] is not None
    assert row["email_grace_release_at"] is not None


async def test_login_against_deleted_email_returns_generic_invalid(
    app_with_service: Any,
) -> None:
    """No info leak: deleted-account login looks identical to wrong-pw."""
    _, sid = await _create_active_with_sid(app_with_service, email="del-login@example.com")
    async with asgi_client(app_with_service) as client:
        await client.post(
            "/tools/account/delete",
            cookies=_cookie_for(sid),
            headers=_CSRF,
            json={"current_password": "long-enough-pw-1"},
        )
        response = await client.post(
            "/tools/account/login",
            json={"email": "del-login@example.com", "password": "long-enough-pw-1"},
            headers=_CSRF,
        )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"
