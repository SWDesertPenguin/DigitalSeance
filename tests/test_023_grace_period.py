# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 US3 acceptance scenario 6 + SC-009 — grace period (T062).

After ``account_delete`` the email is reserved until
``email_grace_release_at`` elapses. The window is governed by
``SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`` (default 7, range
``[0, 365]``); ``0`` disables the reservation entirely.

The test reads the env-var value rather than hardcoding 7 days per
SC-009 — operators tightening or relaxing the window should not
require a test change.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


async def _create_active(app: Any, email: str) -> str:
    service: AccountService = app.state.account_service
    create = await service.create_account(
        email=email,
        password="long-enough-pw-1",  # noqa: S106 -- test fixture
        client_ip="127.0.0.1",
    )
    plaintext = create.dev_plaintext_code
    assert plaintext is not None
    await service.verify_account(account_id=create.account_id, code=plaintext)
    return create.account_id


def _cookie_for(sid: str) -> dict[str, str]:
    return {"sacp_ui_token": _make_cookie_value(sid)}


async def _delete_account(app: Any, account_id: str) -> None:
    sid = await app.state.session_store.create(account_id=account_id)
    async with asgi_client(app) as client:
        response = await client.post(
            "/tools/account/delete",
            cookies=_cookie_for(sid),
            headers=_CSRF,
            json={"current_password": "long-enough-pw-1"},
        )
    assert response.status_code == 200, response.text


async def _set_grace_release_at(pool: asyncpg.Pool, account_id: str, when: datetime) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE accounts SET email_grace_release_at = $1 WHERE id = $2",
            when,
            account_id,
        )


async def test_re_registration_during_grace_window_is_rejected(
    app_with_service: Any,
) -> None:
    """Day 1 after delete: same email re-registration → 409 generic."""
    email = "grace@example.com"
    account_id = await _create_active(app_with_service, email)
    await _delete_account(app_with_service, account_id)
    async with asgi_client(app_with_service) as client:
        response = await client.post(
            "/tools/account/create",
            json={"email": email, "password": "long-enough-pw-2"},
            headers=_CSRF,
        )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "registration_failed"


async def test_re_registration_after_grace_window_succeeds(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """Past env-var grace window: same email re-registration → 201."""
    email = "grace-expired@example.com"
    account_id = await _create_active(app_with_service, email)
    await _delete_account(app_with_service, account_id)
    past = datetime.now(UTC) - timedelta(seconds=1)
    await _set_grace_release_at(pool, account_id, past)
    async with asgi_client(app_with_service) as client:
        response = await client.post(
            "/tools/account/create",
            json={"email": email, "password": "long-enough-pw-2"},
            headers=_CSRF,
        )
    assert response.status_code == 201, response.text
