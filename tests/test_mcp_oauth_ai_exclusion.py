# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test AI participant exclusion from OAuth flows. Spec 030 Phase 4 FR-089, SC-046."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.auth.authorization_server import auth_router

_BASE_PARAMS = {
    "response_type": "code",
    "client_id": "testclient",
    "redirect_uri": "https://example.com/cb",
    "scope": "participant",
    "state": "csrf123",
    "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    "code_challenge_method": "S256",
    "subject": "ai001",
}


def _make_app_with_ai_participant() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)

    client_rec = {
        "client_id": "testclient",
        "redirect_uris": ["https://example.com/cb"],
        "allowed_scopes": ["participant"],
        "registration_status": "approved",
    }
    ai_participant = {"id": "ai001", "provider": "ai", "status": "active"}

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    call_count = 0

    async def _fetchrow_side_effect(sql, *args):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return client_rec
        if call_count == 2:
            return ai_participant
        return {"fail_count": 0}

    mock_conn.fetchrow = _fetchrow_side_effect
    mock_conn.execute = AsyncMock(return_value=None)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)
    app.state.pool = mock_pool
    return app


def test_ai_subject_returns_access_denied() -> None:
    app = _make_app_with_ai_participant()
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/authorize", params=_BASE_PARAMS)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "access_denied" in location


def test_ai_exclusion_produces_redirect_not_json() -> None:
    app = _make_app_with_ai_participant()
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/authorize", params=_BASE_PARAMS)
    assert resp.headers["location"].startswith("https://example.com/cb")
