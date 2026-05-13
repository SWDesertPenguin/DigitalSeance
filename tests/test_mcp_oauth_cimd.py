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
