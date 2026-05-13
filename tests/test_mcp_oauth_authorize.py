# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the OAuth 2.1 /authorize endpoint. Spec 030 Phase 4 FR-070, FR-089."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.auth.authorization_server import auth_router


def _make_app(client_row=None, participant_row=None) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=[client_row, participant_row])
    mock_conn.execute = AsyncMock(return_value=None)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)

    app.state.pool = mock_pool
    return app


_BASE_PARAMS = {
    "response_type": "code",
    "client_id": "testclient",
    "redirect_uri": "https://example.com/cb",
    "scope": "participant tool:session",
    "state": "csrf123",
    "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    "code_challenge_method": "S256",
    "subject": "part001",
}


def test_wrong_challenge_method_returns_error() -> None:
    client_rec = {
        "client_id": "testclient",
        "redirect_uris": ["https://example.com/cb"],
        "allowed_scopes": ["participant", "tool:session"],
        "registration_status": "approved",
    }
    app = _make_app(client_row=client_rec, participant_row=None)
    client = TestClient(app, follow_redirects=False)
    params = {**_BASE_PARAMS, "code_challenge_method": "plain"}
    resp = client.get("/authorize", params=params)
    assert resp.status_code == 302
    assert "unsupported_challenge_method" in resp.headers["location"]


def test_ai_participant_returns_access_denied() -> None:
    client_rec = {
        "client_id": "testclient",
        "redirect_uris": ["https://example.com/cb"],
        "allowed_scopes": ["participant", "tool:session"],
        "registration_status": "approved",
    }
    ai_part = {"id": "ai001", "provider": "ai", "status": "active"}
    app = _make_app(client_row=client_rec, participant_row=ai_part)
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/authorize", params=_BASE_PARAMS)
    assert resp.status_code == 302
    assert "access_denied" in resp.headers["location"]


def test_missing_redirect_uri_returns_400() -> None:
    app = _make_app()
    client = TestClient(app, follow_redirects=False)
    params = {k: v for k, v in _BASE_PARAMS.items() if k != "redirect_uri"}
    resp = client.get("/authorize", params=params)
    assert resp.status_code == 400


def test_unknown_client_returns_400() -> None:
    app = _make_app(client_row=None, participant_row=None)
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/authorize", params=_BASE_PARAMS)
    assert resp.status_code == 400
