# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for refresh token rotation + replay detection. Spec 030 Phase 4 FR-079."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet


def _make_mock_conn(rows: list):
    """Build a mock connection that returns rows in sequence for fetchrow."""
    call_count = 0

    async def _fetchrow(sql, *args):
        nonlocal call_count
        result = rows[call_count] if call_count < len(rows) else None
        call_count += 1
        return result

    conn = AsyncMock()
    conn.fetchrow = _fetchrow
    conn.execute = AsyncMock(return_value=None)
    tr = AsyncMock()
    tr.start = AsyncMock()
    conn.transaction = MagicMock(return_value=tr)
    return conn


@pytest.fixture(autouse=True)
def _set_fernet_key(monkeypatch):
    monkeypatch.setenv("SACP_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_first_issuance_returns_token_pair() -> None:
    from src.mcp_protocol.auth.refresh_token_store import issue_refresh_token

    conn = _make_mock_conn([])
    family_id = "fam001"
    cleartext, thash = await issue_refresh_token(
        conn, client_id="c1", participant_id="p1", scope=["participant"], family_id=family_id
    )
    assert len(cleartext) > 20
    assert thash == hashlib.sha256(cleartext.encode("ascii")).hexdigest()


@pytest.mark.asyncio
async def test_replay_detection_returns_none_and_revokes() -> None:
    from datetime import UTC, datetime

    from src.mcp_protocol.auth.refresh_token_store import rotate_refresh_token

    old_cleartext = "oldtoken_cleartext_abc123"
    old_hash = hashlib.sha256(old_cleartext.encode("ascii")).hexdigest()
    rotated_at = datetime.now(tz=UTC).isoformat()

    already_rotated_row = {
        "token_hash": old_hash,
        "participant_id": "p1",
        "client_id": "c1",
        "scope": ["participant"],
        "family_id": "fam001",
        "rotated_at": rotated_at,
        "revoked_at": None,
        "expires_at": datetime(2030, 1, 1, tzinfo=UTC),
    }
    conn = _make_mock_conn([already_rotated_row])
    conn.transaction = MagicMock()
    tr_mock = AsyncMock()
    tr_mock.__aenter__ = AsyncMock(return_value=None)
    tr_mock.__aexit__ = AsyncMock(return_value=None)
    conn.transaction.return_value = tr_mock

    with patch("src.mcp_protocol.auth.refresh_token_store._family_mod") as mock_fam:
        mock_fam.revoke_family = AsyncMock()
        result = await rotate_refresh_token(conn, old_cleartext, "c1", "p1", ["participant"])

    assert result is None
    mock_fam.revoke_family.assert_called_once()
