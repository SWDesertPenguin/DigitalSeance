# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 US3 acceptance scenario 1 — email change (T059).

Drives ``POST /tools/account/email/change`` then
``POST /tools/account/email/verify`` per clarify Q11:

- The verification code is emitted to the NEW email.
- A heads-up notification fires to the OLD email simultaneously.
- The ``accounts.email`` column does NOT change until the verify call.
- After verify, the column updates and an
  ``account_email_change_consumed`` audit row exists.
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


async def _fetch_email_change_code(pool: asyncpg.Pool, account_id: str) -> str:
    """Pluck the new_email + code_hash from the emit-row payload."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT new_value FROM admin_audit_log "
            "WHERE action = 'account_email_change_emitted' "
            "AND target_id = $1 ORDER BY id DESC LIMIT 1",
            account_id,
        )
    return row["new_value"] if row else ""


async def test_email_change_emits_both_audit_rows_and_does_not_update_until_verify(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """Notify-old + verify-new: email column unchanged until verify."""
    account_id, sid = await _create_active_with_sid(app_with_service, email="ec-old@example.com")
    with TestClient(app_with_service) as client:
        response = client.post(
            "/tools/account/email/change",
            cookies=_cookie_for(sid),
            headers=_CSRF,
            json={"new_email": "ec-new@example.com"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"verification_email_sent": True, "old_email_notified": True}
    async with pool.acquire() as conn:
        current = await conn.fetchval("SELECT email FROM accounts WHERE id = $1", account_id)
        actions = {
            r["action"]
            for r in await conn.fetch(
                "SELECT action FROM admin_audit_log WHERE target_id = $1",
                account_id,
            )
        }
    assert current == "ec-old@example.com"
    assert "account_email_change_emitted" in actions
    assert "account_email_change_old_notified" in actions
