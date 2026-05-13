# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the OAuth 2.1 /token endpoint. Spec 030 Phase 4 FR-073, FR-079."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.auth.token_endpoint import token_router


def _make_app(pool=None) -> FastAPI:
    app = FastAPI()
    app.include_router(token_router)
    if pool:
        app.state.pool = pool
    return app


def test_unsupported_grant_type() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/token",
        data={"grant_type": "password", "username": "x", "password": "y"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_grant_type"


def test_authorization_code_grant_missing_params() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/token", data={"grant_type": "authorization_code"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_request"


def test_refresh_token_grant_missing_params() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/token", data={"grant_type": "refresh_token"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_request"


def test_authorization_code_grant_no_db() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": "fakecode",
            "code_verifier": "fakeverifier",
            "redirect_uri": "https://example.com/cb",
            "client_id": "testclient",
        },
    )
    assert resp.status_code in (400, 500)
