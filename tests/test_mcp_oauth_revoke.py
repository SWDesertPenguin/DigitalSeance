# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the OAuth 2.1 /revoke endpoint per RFC 7009. Spec 030 Phase 4 FR-074."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.auth.revocation_endpoint import revocation_router


def _make_app(pool=None) -> FastAPI:
    app = FastAPI()
    app.include_router(revocation_router)
    if pool:
        app.state.pool = pool
    return app


def test_revoke_unknown_token_returns_200() -> None:
    """RFC 7009: unknown tokens must return 200, not an error."""
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/revoke", data={"token": "totally_unknown_token_xyz"})
    assert resp.status_code == 200


def test_revoke_missing_token_returns_422() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/revoke", data={})
    assert resp.status_code == 422


def test_revoke_with_invalid_client_returns_400() -> None:
    from unittest.mock import AsyncMock, MagicMock

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock(return_value=None)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=mock_ctx)

    mock_conn.fetchrow = AsyncMock(
        side_effect=[
            {"client_id": "c1", "registration_status": "revoked"},
        ]
    )

    app = _make_app(pool=mock_pool)
    client = TestClient(app)
    resp = client.post("/revoke", data={"token": "tok", "client_id": "c1"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_client"
