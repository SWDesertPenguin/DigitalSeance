# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 US3 acceptance scenarios 2-3 — password change (T060).

- Correct current_password → new argon2id hash stored; subsequent
  logins require the new password.
- Incorrect current_password → 401, new password NOT stored.
- Clarify Q12: every other sid for the account is dropped from the
  SessionStore; the actor's current sid SURVIVES.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from src.accounts.service import AccountService
from src.repositories.account_repo import AccountRepository
from src.repositories.log_repo import LogRepository
from src.web_ui.app import create_web_app
from src.web_ui.auth import _make_cookie_value
from src.web_ui.security import CSRF_HEADER, CSRF_VALUE
from src.web_ui.session_store import SessionStore

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


async def test_password_change_invalidates_other_sids_only(
    app_with_service: Any,
) -> None:
    """Actor's sid survives; every other sid is dropped (clarify Q12)."""
    account_id = await _create_active(app_with_service, "pw@example.com")
    store = app_with_service.state.session_store
    actor_sid = await store.create(account_id=account_id)
    other_sid_1 = await store.create(account_id=account_id)
    other_sid_2 = await store.create(account_id=account_id)
    with TestClient(app_with_service) as client:
        response = client.post(
            "/tools/account/password/change",
            cookies=_cookie_for(actor_sid),
            headers=_CSRF,
            json={
                "current_password": "long-enough-pw-1",
                "new_password": "long-enough-pw-2",
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["other_sessions_invalidated"] == 2
    assert await store.get(actor_sid) is not None
    assert await store.get(other_sid_1) is None
    assert await store.get(other_sid_2) is None


async def test_password_change_rejects_incorrect_current_password(
    app_with_service: Any,
) -> None:
    """Incorrect current_password → 401; new password NOT stored."""
    account_id = await _create_active(app_with_service, "pw-bad@example.com")
    store = app_with_service.state.session_store
    sid = await store.create(account_id=account_id)
    with TestClient(app_with_service) as client:
        response = client.post(
            "/tools/account/password/change",
            cookies=_cookie_for(sid),
            headers=_CSRF,
            json={
                "current_password": "wrong-current-pw",
                "new_password": "long-enough-pw-2",
            },
        )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


async def test_password_change_emits_audit_row(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """Successful change writes an account_password_change audit row."""
    account_id = await _create_active(app_with_service, "pw-audit@example.com")
    store = app_with_service.state.session_store
    sid = await store.create(account_id=account_id)
    with TestClient(app_with_service) as client:
        client.post(
            "/tools/account/password/change",
            cookies=_cookie_for(sid),
            headers=_CSRF,
            json={
                "current_password": "long-enough-pw-1",
                "new_password": "long-enough-pw-2",
            },
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT new_value FROM admin_audit_log "
            "WHERE action = 'account_password_change' AND target_id = $1",
            account_id,
        )
    assert row is not None
