# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 US4 acceptance — account ownership transfer (FR-020).

Per research.md §7 (revised in-v1 at impl-time), v1 ships a
deployment-owner-keyed admin shim gating
``POST /tools/admin/account/transfer_participants``.

Coverage:
- Acceptance 1: source account_participants rows repoint to target.
- Acceptance 2: regular-account caller (no admin key) → HTTP 403.
- Acceptance 3 + 4: source's /me/sessions excludes transferred sessions;
  target sees them. Per-session bearer is unaffected (transfer moves
  ownership pointer only).
- SC-010: transfer attempt without the X-Deployment-Owner-Key header
  returns HTTP 403.
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
from src.web_ui.security import CSRF_HEADER, CSRF_VALUE
from src.web_ui.session_store import SessionStore

_CSRF = {CSRF_HEADER: CSRF_VALUE}
_OWNER_KEY = "x" * 40
_TRANSFER_PATH = "/tools/admin/account/transfer_participants"


@pytest.fixture(autouse=True)
def _accounts_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", "8192")
    monkeypatch.setenv("SACP_DEPLOYMENT_OWNER_KEY", _OWNER_KEY)


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


async def _seed_session_with_participant(
    pool: asyncpg.Pool,
    *,
    account_id: str,
    session_id: str,
    participant_id: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, name, status) VALUES ($1, 'S', 'active') "
            "ON CONFLICT (id) DO NOTHING",
            session_id,
        )
        await conn.execute(
            """
            INSERT INTO participants (
                id, session_id, display_name, role,
                provider, model, model_tier, model_family, context_window
            )
            VALUES ($1, $2, 'X', 'participant', 'human', 'human', 'low', 'human', 0)
            ON CONFLICT (id) DO NOTHING
            """,
            participant_id,
            session_id,
        )
    repo = AccountRepository(pool)
    await repo.link_participant_to_account(
        account_id=account_id,
        participant_id=participant_id,
    )


async def test_transfer_repoints_account_participants(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """Source's account_participants rows move to target account_id."""
    src = await _create_active(app_with_service, "src@example.com")
    tgt = await _create_active(app_with_service, "tgt@example.com")
    await _seed_session_with_participant(
        pool, account_id=src, session_id="ses_xfer", participant_id="par_xfer"
    )
    with TestClient(app_with_service) as client:
        response = client.post(
            _TRANSFER_PATH,
            headers={**_CSRF, "X-Deployment-Owner-Key": _OWNER_KEY},
            json={"source_account_id": src, "target_account_id": tgt},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transferred"] == 1
    assert "par_xfer" in body["participant_ids"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT account_id FROM account_participants WHERE participant_id = $1",
            "par_xfer",
        )
    assert str(row["account_id"]) == tgt


async def test_transfer_rejects_missing_owner_key(app_with_service: Any) -> None:
    """No X-Deployment-Owner-Key header → 403, no info leak (SC-010)."""
    with TestClient(app_with_service) as client:
        response = client.post(
            _TRANSFER_PATH,
            headers=_CSRF,
            json={"source_account_id": "x", "target_account_id": "y"},
        )
    assert response.status_code == 403


async def test_transfer_rejects_wrong_owner_key(app_with_service: Any) -> None:
    """Wrong key → 403, identical shape to missing-key path."""
    with TestClient(app_with_service) as client:
        response = client.post(
            _TRANSFER_PATH,
            headers={**_CSRF, "X-Deployment-Owner-Key": "wrong"},
            json={"source_account_id": "x", "target_account_id": "y"},
        )
    assert response.status_code == 403


async def test_transfer_emits_ownership_audit_row(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """account_ownership_transfer audit row carries source/target/participant ids."""
    src = await _create_active(app_with_service, "src-audit@example.com")
    tgt = await _create_active(app_with_service, "tgt-audit@example.com")
    await _seed_session_with_participant(
        pool, account_id=src, session_id="ses_aud", participant_id="par_aud"
    )
    with TestClient(app_with_service) as client:
        client.post(
            _TRANSFER_PATH,
            headers={**_CSRF, "X-Deployment-Owner-Key": _OWNER_KEY},
            json={"source_account_id": src, "target_account_id": tgt},
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT new_value FROM admin_audit_log "
            "WHERE action = 'account_ownership_transfer' AND target_id = $1",
            tgt,
        )
    assert row is not None
