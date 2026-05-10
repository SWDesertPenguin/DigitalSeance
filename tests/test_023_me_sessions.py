# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 US2 acceptance scenarios — /me/sessions (T050-T053).

Drives ``GET /me/sessions`` and ``POST /me/sessions/{session_id}/rebind``
against the real Postgres pool with a wired ``AccountService``.

Coverage:

- Acceptance 1-2: segmented response shape, per-entry fields.
- Acceptance 3: cross-account isolation (FR-009 / SC-004).
- Acceptance 4: empty account returns empty arrays, not 404.
- Acceptance 5: pagination per segment at 50/page (FR-008 / clarify Q7).
- Acceptance 6: rebind binds the existing sid to the per-session
  participant credential (FR-016).
- FR-008 10K-threshold trip: structured WARN + audit row, idempotent.
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
    account_repo = AccountRepository(pool)
    app.state.log_repo = log_repo
    app.state.session_store = session_store
    app.state.account_repo = account_repo
    app.state.account_service = AccountService(
        account_repo=account_repo,
        log_repo=log_repo,
        session_store=session_store,
    )
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_session(pool: asyncpg.Pool, session_id: str, status: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, name, status) VALUES ($1, $2, $3) "
            "ON CONFLICT (id) DO NOTHING",
            session_id,
            f"Session {session_id}",
            status,
        )


async def _seed_participant(
    pool: asyncpg.Pool,
    *,
    participant_id: str,
    session_id: str,
    role: str = "participant",
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO participants (
                id, session_id, display_name, role,
                provider, model, model_tier, model_family, context_window
            )
            VALUES ($1, $2, 'Test User', $3, 'human', 'human', 'low', 'human', 0)
            ON CONFLICT (id) DO NOTHING
            """,
            participant_id,
            session_id,
            role,
        )


async def _create_account_with_sid(
    app: Any,
    *,
    email: str,
) -> tuple[str, str]:
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


async def _bind_participant(
    pool: asyncpg.Pool,
    *,
    account_id: str,
    participant_id: str,
) -> None:
    repo = AccountRepository(pool)
    await repo.link_participant_to_account(
        account_id=account_id,
        participant_id=participant_id,
    )


async def _seed_owned_session(
    app: Any,
    pool: asyncpg.Pool,
    *,
    account_id: str,
    session_id: str,
    participant_id: str,
    status: str,
    role: str = "participant",
) -> None:
    """Insert session, participant, and account_participants binding."""
    await _seed_session(pool, session_id, status)
    await _seed_participant(
        pool,
        participant_id=participant_id,
        session_id=session_id,
        role=role,
    )
    await _bind_participant(
        pool,
        account_id=account_id,
        participant_id=participant_id,
    )


# ---------------------------------------------------------------------------
# Acceptance 1-2: segmented shape + per-entry fields
# ---------------------------------------------------------------------------


async def _seed_owned_pair(
    app: Any,
    pool: asyncpg.Pool,
    *,
    account_id: str,
    pairs: list[tuple[str, str, str]],
) -> None:
    for session_id, participant_id, status in pairs:
        await _seed_owned_session(
            app,
            pool,
            account_id=account_id,
            session_id=session_id,
            participant_id=participant_id,
            status=status,
        )


async def test_me_sessions_returns_segmented_shape(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """Active + paused → active_sessions; archived → archived_sessions."""
    account_id, sid = await _create_account_with_sid(app_with_service, email="seg@example.com")
    await _seed_owned_pair(
        app_with_service,
        pool,
        account_id=account_id,
        pairs=[
            ("ses_seg_active", "par_seg_active", "active"),
            ("ses_seg_archived", "par_seg_archived", "archived"),
        ],
    )
    with TestClient(app_with_service) as client:
        body = client.get("/me/sessions", cookies=_cookie_for(sid)).json()
    assert {s["session_id"] for s in body["active_sessions"]} == {"ses_seg_active"}
    assert {s["session_id"] for s in body["archived_sessions"]} == {"ses_seg_archived"}
    assert body["active_sessions"][0]["role"] == "participant"
    assert body["active_sessions"][0]["participant_id"] == "par_seg_active"


# ---------------------------------------------------------------------------
# Acceptance 3: cross-account isolation
# ---------------------------------------------------------------------------


async def test_me_sessions_does_not_leak_other_accounts_sessions(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """A's /me/sessions never returns sessions B owns (FR-009 / SC-004)."""
    account_a, sid_a = await _create_account_with_sid(app_with_service, email="a@example.com")
    account_b, _ = await _create_account_with_sid(app_with_service, email="b@example.com")
    await _seed_owned_session(
        app_with_service,
        pool,
        account_id=account_a,
        session_id="ses_iso_a",
        participant_id="par_iso_a",
        status="active",
    )
    await _seed_owned_session(
        app_with_service,
        pool,
        account_id=account_b,
        session_id="ses_iso_b",
        participant_id="par_iso_b",
        status="active",
    )
    with TestClient(app_with_service) as client:
        response = client.get("/me/sessions", cookies=_cookie_for(sid_a))
    body = response.json()
    ids = {s["session_id"] for s in body["active_sessions"]}
    assert "ses_iso_a" in ids
    assert "ses_iso_b" not in ids


# ---------------------------------------------------------------------------
# Acceptance 4: empty account returns empty arrays
# ---------------------------------------------------------------------------


async def test_me_sessions_empty_account_returns_empty_arrays(
    app_with_service: Any,
) -> None:
    """An account with zero joined sessions returns empty arrays, not 404."""
    _, sid = await _create_account_with_sid(app_with_service, email="empty@example.com")
    with TestClient(app_with_service) as client:
        response = client.get("/me/sessions", cookies=_cookie_for(sid))
    assert response.status_code == 200
    body = response.json()
    assert body["active_sessions"] == []
    assert body["archived_sessions"] == []
    assert body["active_next_offset"] is None
    assert body["archived_next_offset"] is None


# ---------------------------------------------------------------------------
# Acceptance 5: pagination per segment
# ---------------------------------------------------------------------------


async def test_me_sessions_paginates_per_segment(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """active_offset advances within active; archived offset is independent."""
    account_id, sid = await _create_account_with_sid(app_with_service, email="page@example.com")
    for i in range(55):
        await _seed_owned_session(
            app_with_service,
            pool,
            account_id=account_id,
            session_id=f"ses_page_active_{i:02d}",
            participant_id=f"par_page_active_{i:02d}",
            status="active",
        )
    with TestClient(app_with_service) as client:
        first = client.get("/me/sessions", cookies=_cookie_for(sid)).json()
        assert len(first["active_sessions"]) == 50
        assert first["active_next_offset"] == 50
        second = client.get(
            "/me/sessions?active_offset=50",
            cookies=_cookie_for(sid),
        ).json()
    assert len(second["active_sessions"]) == 5
    assert second["active_next_offset"] is None


# ---------------------------------------------------------------------------
# Acceptance 6: rebind binds existing sid to per-session credential
# ---------------------------------------------------------------------------


async def test_rebind_populates_session_entry_with_participant(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """POST /me/sessions/{id}/rebind sets participant_id + session_id on entry."""
    account_id, sid = await _create_account_with_sid(app_with_service, email="rebind@example.com")
    await _seed_owned_session(
        app_with_service,
        pool,
        account_id=account_id,
        session_id="ses_rebind",
        participant_id="par_rebind",
        status="active",
    )
    with TestClient(app_with_service) as client:
        response = client.post(
            "/me/sessions/ses_rebind/rebind",
            cookies=_cookie_for(sid),
            headers=_CSRF,
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == "ses_rebind"
    assert body["participant_id"] == "par_rebind"
    entry = await app_with_service.state.session_store.get(sid)
    assert entry is not None
    assert entry.account_id == account_id
    assert entry.participant_id == "par_rebind"
    assert entry.session_id == "ses_rebind"


async def test_rebind_404_when_account_does_not_own_participant(
    app_with_service: Any,
    pool: asyncpg.Pool,
) -> None:
    """Rebind to a session the account doesn't own returns 404, no leak."""
    _, sid = await _create_account_with_sid(app_with_service, email="other@example.com")
    await _seed_session(pool, "ses_unowned", "active")
    await _seed_participant(pool, participant_id="par_unowned", session_id="ses_unowned")
    with TestClient(app_with_service) as client:
        response = client.post(
            "/me/sessions/ses_unowned/rebind",
            cookies=_cookie_for(sid),
            headers=_CSRF,
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# FR-008 10K-threshold trip — idempotent
# ---------------------------------------------------------------------------


async def _count_threshold_audit_rows(pool: asyncpg.Pool, account_id: str) -> int:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM admin_audit_log "
            "WHERE action = 'account_session_count_threshold_tripped' "
            "AND target_id = $1",
            account_id,
        )
    return len(rows)


async def test_me_sessions_emits_threshold_audit_when_count_exceeds_10k(
    app_with_service: Any,
    pool: asyncpg.Pool,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic count crossing emits one structured WARN + one audit row."""
    import logging

    import src.accounts.service as service_module

    monkeypatch.setattr(service_module, "_SESSION_COUNT_THRESHOLD", 1)
    caplog.set_level(logging.WARNING)
    account_id, sid = await _create_account_with_sid(app_with_service, email="thresh@example.com")
    pairs = [(f"ses_thresh_{i}", f"par_thresh_{i}", "active") for i in range(2)]
    await _seed_owned_pair(app_with_service, pool, account_id=account_id, pairs=pairs)
    with TestClient(app_with_service) as client:
        client.get("/me/sessions", cookies=_cookie_for(sid))
        client.get("/me/sessions", cookies=_cookie_for(sid))
    warns = [r for r in caplog.records if "threshold" in r.getMessage().lower()]
    assert len(warns) == 1, "FR-008 trip should be idempotent within process"
    assert await _count_threshold_audit_rows(pool, account_id) == 1
