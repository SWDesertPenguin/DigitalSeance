# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opaque cursor encoding for paginated MCP tools. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

import base64
import json


def encode_cursor(last_id: str, sort_key_value: str) -> str:
    """Return an opaque base64-encoded cursor from (last_id, sort_key_value)."""
    payload = json.dumps({"i": last_id, "k": sort_key_value}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, str]:
    """Decode a cursor produced by encode_cursor; raise ValueError on invalid input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(raw)
        return str(data["i"]), str(data["k"])
    except Exception as exc:
        raise ValueError(f"invalid cursor: {cursor!r}") from exc
