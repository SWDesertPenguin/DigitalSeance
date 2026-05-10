# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 US1 acceptance scenario 6 + SC-006 (T039).

Drives the per-IP login rate limiter (FR-015): repeated login attempts
from the same IP trip the threshold and produce HTTP 429 with a
``Retry-After`` header. Mirrors spec 009 §FR-002 / FR-003 shape.

The limiter state is process-local (per ``LoginRateLimiter``), so each
test constructs its own ``AccountService`` with a low threshold to
trip quickly without burning argon2id cycles.
"""

from __future__ import annotations

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
async def app_with_low_threshold(pool: asyncpg.Pool) -> Any:
    """Wire a small-threshold rate limiter so the test trips in 4 calls."""
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
        rate_limiter=LoginRateLimiter(threshold=3),
    )
    return app


# ---------------------------------------------------------------------------
# Scenario 6: per-IP threshold trip → 429 + Retry-After
# ---------------------------------------------------------------------------


async def test_login_rate_limit_trips_at_threshold(
    app_with_low_threshold: Any,
) -> None:
    """The 4th call from the same IP returns 429 + Retry-After."""
    with TestClient(app_with_low_threshold) as client:
        responses = [
            client.post(
                "/tools/account/login",
                json={"email": "x@example.com", "password": "any-password-12"},
                headers=_CSRF,
            )
            for _ in range(4)
        ]
    # First three return 401 (invalid_credentials); the fourth trips
    # the threshold and returns 429 + Retry-After.
    assert [r.status_code for r in responses[:3]] == [401, 401, 401]
    assert responses[3].status_code == 429
    assert responses[3].json()["detail"]["error"] == "rate_limit_exceeded"
    retry_after = responses[3].headers.get("Retry-After")
    assert retry_after is not None
    assert int(retry_after) >= 1


def _login_at_ip(client: TestClient, ip: str) -> int:
    response = client.post(
        "/tools/account/login",
        json={"email": "x@example.com", "password": "any-password-12"},
        headers={**_CSRF, "X-Forwarded-For": ip},
    )
    return response.status_code


async def test_login_rate_limit_per_ip_isolation(
    app_with_low_threshold: Any,
) -> None:
    """A second client at a different IP isn't affected by the first's trips."""
    import os

    os.environ["SACP_TRUST_PROXY"] = "1"
    try:
        with TestClient(app_with_low_threshold) as client:
            for _ in range(3):
                _login_at_ip(client, "10.0.0.1")
            assert _login_at_ip(client, "10.0.0.1") == 429
            assert _login_at_ip(client, "10.0.0.2") == 401
    finally:
        os.environ.pop("SACP_TRUST_PROXY", None)


async def test_login_rate_limit_emits_failed_audit_row(
    app_with_low_threshold: Any,
    pool: asyncpg.Pool,
) -> None:
    """A 429 trip writes account_login_failed with rate_limit_exceeded reason."""
    with TestClient(app_with_low_threshold) as client:
        for _ in range(4):
            client.post(
                "/tools/account/login",
                json={"email": "rate@example.com", "password": "any-password-12"},
                headers=_CSRF,
            )
    async with pool.acquire() as conn:
        rate_rows = await conn.fetch(
            "SELECT new_value FROM admin_audit_log "
            "WHERE action = 'account_login_failed' "
            "AND new_value LIKE '%rate_limit_exceeded%'",
        )
    assert len(rate_rows) >= 1
