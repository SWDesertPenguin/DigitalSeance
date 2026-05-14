# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for CIMD fetch + validation. Spec 030 Phase 4 FR-073."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_protocol.auth.client_registration import fetch_and_validate_cimd


@pytest.mark.asyncio
async def test_oversized_body_rejected() -> None:
    big_body = b"x" * (256 * 1024 + 1)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = big_body

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="byte limit"):
            await fetch_and_validate_cimd("https://example.com/cimd.json", [])


@pytest.mark.asyncio
async def test_malformed_json_rejected() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"not json {"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not valid JSON"):
            await fetch_and_validate_cimd("https://example.com/cimd.json", [])


@pytest.mark.asyncio
async def test_valid_cimd_accepted() -> None:
    doc = {"redirect_uris": ["https://example.com/cb"], "client_name": "Test Client"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = json.dumps(doc).encode()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await fetch_and_validate_cimd("https://example.com/cimd.json", [])
    assert result["client_name"] == "Test Client"


@pytest.mark.asyncio
async def test_non_allowlisted_host_rejected() -> None:
    doc = {"redirect_uris": ["https://bad.example.com/cb"], "client_name": "Bad"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = json.dumps(doc).encode()

    with pytest.raises(ValueError, match="not in allowed list"):
        await fetch_and_validate_cimd("https://bad.example.com/cimd.json", ["allowed.example.com"])


# ---------------------------------------------------------------------------
# SSRF defence
# ---------------------------------------------------------------------------


def _addrinfo(ip: str, family: int) -> tuple:
    return (family, 1, 6, "", (ip, 443) if family == 2 else (ip, 443, 0, 0))


@pytest.mark.asyncio
async def test_http_scheme_rejected_by_default() -> None:
    with pytest.raises(ValueError, match="must use https"):
        await fetch_and_validate_cimd("http://example.com/cimd.json", [])


@pytest.mark.asyncio
async def test_loopback_ip_rejected() -> None:
    with (
        patch("socket.getaddrinfo", return_value=[_addrinfo("127.0.0.1", 2)]),
        pytest.raises(ValueError, match="internal address"),
    ):
        await fetch_and_validate_cimd("https://attacker.example/cimd.json", [])


@pytest.mark.asyncio
async def test_rfc1918_ip_rejected() -> None:
    with (
        patch("socket.getaddrinfo", return_value=[_addrinfo("10.0.0.5", 2)]),
        pytest.raises(ValueError, match="internal address"),
    ):
        await fetch_and_validate_cimd("https://attacker.example/cimd.json", [])


@pytest.mark.asyncio
async def test_link_local_ip_rejected() -> None:
    with (
        patch("socket.getaddrinfo", return_value=[_addrinfo("169.254.10.5", 2)]),
        pytest.raises(ValueError, match="internal address"),
    ):
        await fetch_and_validate_cimd("https://attacker.example/cimd.json", [])


@pytest.mark.asyncio
async def test_cloud_metadata_literal_rejected() -> None:
    with pytest.raises(ValueError, match="blocked address"):
        await fetch_and_validate_cimd("https://169.254.169.254/cimd.json", [])


@pytest.mark.asyncio
async def test_ipv6_loopback_rejected() -> None:
    with (
        patch("socket.getaddrinfo", return_value=[_addrinfo("::1", 10)]),
        pytest.raises(ValueError, match="internal address"),
    ):
        await fetch_and_validate_cimd("https://attacker.example/cimd.json", [])


@pytest.mark.asyncio
async def test_dns_rebind_blocked_by_ip_pinning() -> None:
    """The fetch must connect to the IP resolved during pre-fetch validation
    so an attacker who controls DNS cannot rebind the hostname to an internal
    address between `_enforce_ssrf_safe_target` and the actual GET.
    """
    doc = {"redirect_uris": ["https://attacker.example/cb"], "client_name": "X"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = json.dumps(doc).encode()

    captured: dict = {}

    async def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["extensions"] = kwargs.get("extensions", {})
        return mock_resp

    with (
        patch("socket.getaddrinfo", return_value=[_addrinfo("8.8.8.8", 2)]),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=fake_get)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        await fetch_and_validate_cimd("https://attacker.example/cimd.json", [])

    assert captured["url"] == "https://8.8.8.8/cimd.json"
    assert captured["headers"]["Host"] == "attacker.example"
    assert captured["extensions"]["sni_hostname"] == "attacker.example"


@pytest.mark.asyncio
async def test_dns_failure_rejected() -> None:
    import socket as _socket

    with (
        patch("socket.getaddrinfo", side_effect=_socket.gaierror("no resolve")),
        pytest.raises(ValueError, match="does not resolve"),
    ):
        await fetch_and_validate_cimd("https://no-such-host.example/cimd.json", [])
