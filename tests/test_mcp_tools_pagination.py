# SPDX-License-Identifier: AGPL-3.0-or-later
"""T101: cursor encoding round-trip. Spec 030 Phase 3."""

from __future__ import annotations

import pytest

from src.mcp_protocol.pagination import decode_cursor, encode_cursor


def test_encode_decode_roundtrip() -> None:
    cursor = encode_cursor("abc123", "2024-01-01T00:00:00")
    last_id, sort_key = decode_cursor(cursor)
    assert last_id == "abc123"
    assert sort_key == "2024-01-01T00:00:00"


def test_cursor_is_opaque_base64() -> None:
    cursor = encode_cursor("id1", "val1")
    assert cursor.isascii()
    assert " " not in cursor


def test_decode_invalid_cursor_raises_value_error() -> None:
    with pytest.raises(ValueError):
        decode_cursor("not-valid-base64!!!")


def test_decode_missing_fields_raises() -> None:
    import base64
    import json

    bad = base64.urlsafe_b64encode(json.dumps({"x": 1}).encode()).decode()
    with pytest.raises(ValueError):
        decode_cursor(bad)


def test_encode_empty_strings() -> None:
    cursor = encode_cursor("", "")
    last_id, sort_key = decode_cursor(cursor)
    assert last_id == ""
    assert sort_key == ""
