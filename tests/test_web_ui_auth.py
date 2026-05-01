"""Web UI auth-path error translation (spec 002 / audit H-01).

Verifies `_authenticate_or_raise` returns only the generic `"IP binding
mismatch"` detail in the 403 body when `IPBindingMismatchError` fires —
never echoes the bound IP, the request IP, or any other fragment of
the underlying exception message.

Pairs with the MCP equivalent in src/mcp_server/middleware.py which has
always returned the generic string. Closes the asymmetry that audit H-01
flagged.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.repositories.errors import (
    AuthRequiredError,
    IPBindingMismatchError,
    TokenExpiredError,
    TokenInvalidError,
)
from src.web_ui.auth import _authenticate_or_raise


class _FakeAuthService:
    """Stand-in for AuthService — raises whatever exc is constructed with."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def authenticate(self, token: str, client_ip: str) -> None:
        raise self._exc


class _FakeClient:
    host = "192.0.2.1"  # RFC 5737 TEST-NET-1


class _FakeRequest:
    """Just enough Request shape for _authenticate_or_raise."""

    client = _FakeClient()


@pytest.mark.asyncio
async def test_ip_binding_mismatch_403_omits_ip_fragments() -> None:
    """403 detail must be the generic constant — no bound-IP leak (H-01)."""
    leaky = IPBindingMismatchError(
        "Session bound to 198.51.100.42, request from 203.0.113.7",
    )
    service = _FakeAuthService(leaky)

    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_or_raise(service, "fake-token", _FakeRequest())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "IP binding mismatch"
    detail = str(exc_info.value.detail)
    assert "198.51.100.42" not in detail
    assert "203.0.113.7" not in detail
    assert "Session bound to" not in detail


@pytest.mark.asyncio
async def test_token_expired_translates_to_401() -> None:
    """Sanity check the expired-token path is unchanged by the H-01 fix."""
    service = _FakeAuthService(TokenExpiredError("expired"))
    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_or_raise(service, "fake-token", _FakeRequest())
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token expired"


@pytest.mark.asyncio
async def test_invalid_token_translates_to_401() -> None:
    """Sanity check the invalid-token path is unchanged."""
    service = _FakeAuthService(TokenInvalidError("invalid"))
    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_or_raise(service, "fake-token", _FakeRequest())
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


@pytest.mark.asyncio
async def test_auth_required_translates_to_401() -> None:
    """Sanity check the missing-token path is unchanged."""
    service = _FakeAuthService(AuthRequiredError("required"))
    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_or_raise(service, "fake-token", _FakeRequest())
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"
