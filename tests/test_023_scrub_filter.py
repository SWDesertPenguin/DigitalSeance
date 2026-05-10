# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 SC-012 ScrubFilter coverage (T042).

Drives the create + verify + login flows and asserts that:

- No plaintext password ever appears in any captured log line.
- No 16-character base32 verification code appears in plaintext outside
  the noop adapter's ``_dev_plaintext`` field (research §6 + FR-014).
- No email body content (the noop adapter writes only ``body_length``
  to the audit row, never the body text) appears in any log line.

Phase 5's T067 lands the explicit ScrubFilter regex extensions in
``src/security/scrubber.py``. This test enforces the contract today:
the application code MUST NOT log secrets via :mod:`logging` (the
existing ScrubFilter, plus the audit-log shape, plus the
no-plaintext-in-handler discipline together produce the contract).
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from src.accounts.rate_limit import LoginRateLimiter
from src.accounts.service import AccountService
from src.repositories.account_repo import AccountRepository
from src.repositories.log_repo import LogRepository
from src.web_ui.app import create_web_app
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
    app.state.log_repo = log_repo
    app.state.session_store = session_store
    app.state.account_service = AccountService(
        account_repo=AccountRepository(pool),
        log_repo=log_repo,
        session_store=session_store,
        rate_limiter=LoginRateLimiter(threshold=1000),
    )
    return app


# Pinned plaintext + body content the test asserts NEVER appear in logs.
_PLAINTEXT_PASSWORD = "secret-password-12345-do-not-leak"  # noqa: S105 -- test fixture
_PINNED_BODY_FRAGMENT = "Your verification code"


async def _drive_create_verify_login(app: Any, email: str) -> str:
    service: AccountService = app.state.account_service
    create = await service.create_account(
        email=email,
        password=_PLAINTEXT_PASSWORD,
        client_ip="127.0.0.1",
    )
    plaintext_code = create.dev_plaintext_code
    assert plaintext_code is not None
    await service.verify_account(account_id=create.account_id, code=plaintext_code)
    with TestClient(app) as client:
        client.post(
            "/tools/account/login",
            json={"email": email, "password": _PLAINTEXT_PASSWORD},
            headers=_CSRF,
        )
    return plaintext_code


async def test_no_password_or_code_in_log_capture(
    app_with_service: Any,
    pool: asyncpg.Pool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Drive create + verify + login; no plaintext leaks via logging."""
    caplog.set_level(logging.DEBUG)
    plaintext_code = await _drive_create_verify_login(app_with_service, "scrub@example.com")
    captured = "\n".join(record.getMessage() for record in caplog.records)
    assert _PLAINTEXT_PASSWORD not in captured
    assert plaintext_code not in captured
    assert _PINNED_BODY_FRAGMENT not in captured


async def test_audit_log_payload_does_not_carry_plaintext_password(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """No admin_audit_log row carries the plaintext password."""
    service: AccountService = app_with_service.state.account_service
    create = await service.create_account(
        email="payload@example.com",
        password=_PLAINTEXT_PASSWORD,
        client_ip="127.0.0.1",
    )
    plaintext_code = create.dev_plaintext_code
    assert plaintext_code is not None
    await service.verify_account(account_id=create.account_id, code=plaintext_code)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT new_value FROM admin_audit_log WHERE target_id = $1",
            create.account_id,
        )
    for row in rows:
        new_value = row["new_value"] or ""
        assert (
            _PLAINTEXT_PASSWORD not in new_value
        ), f"plaintext password found in audit row payload: {new_value!r}"


async def test_audit_emit_row_carries_only_code_hash_not_plaintext(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """The account_verification_emitted row stores ONLY the HMAC hash."""
    service: AccountService = app_with_service.state.account_service
    create = await service.create_account(
        email="hash-only@example.com",
        password=_PLAINTEXT_PASSWORD,
        client_ip="127.0.0.1",
    )
    plaintext_code = create.dev_plaintext_code
    assert plaintext_code is not None

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT new_value FROM admin_audit_log "
            "WHERE target_id = $1 AND action = 'account_verification_emitted'",
            create.account_id,
        )
    assert row is not None
    payload_text = row["new_value"]
    assert (
        plaintext_code not in payload_text
    ), f"plaintext code leaked into emit-row payload: {payload_text!r}"
    assert "code_hash" in payload_text
