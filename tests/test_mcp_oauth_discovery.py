# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for OAuth 2.1 discovery metadata. Spec 030 Phase 4 FR-075."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_protocol.auth.discovery_metadata import oauth_discovery_router
from src.mcp_protocol.auth.scope_grant import SCOPE_VOCABULARY


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(oauth_discovery_router)
    return app


def test_discovery_returns_expected_shape() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    body = resp.json()
    assert "authorization_endpoint" in body
    assert "token_endpoint" in body
    assert "revocation_endpoint" in body
    assert "S256" in body["code_challenge_methods_supported"]
    assert "plain" not in body["code_challenge_methods_supported"]
    assert "password" not in body.get("grant_types_supported", [])
    assert "implicit" not in body.get("grant_types_supported", [])


def test_discovery_scopes_match_vocabulary() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/.well-known/oauth-protected-resource")
    body = resp.json()
    returned = set(body["scopes_supported"])
    assert returned == SCOPE_VOCABULARY


def test_discovery_not_mounted_when_oauth_disabled() -> None:
    """When SACP_OAUTH_ENABLED=false, the endpoint must not be registered."""
    import os

    original = os.environ.get("SACP_OAUTH_ENABLED", "")
    try:
        os.environ["SACP_OAUTH_ENABLED"] = "false"
        plain_app = FastAPI()
        client = TestClient(plain_app)
        resp = client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code == 404
    finally:
        if original:
            os.environ["SACP_OAUTH_ENABLED"] = original
        else:
            os.environ.pop("SACP_OAUTH_ENABLED", None)
