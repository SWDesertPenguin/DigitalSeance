# SPDX-License-Identifier: AGPL-3.0-or-later

"""HMAC-keyed token-lookup helpers for indexed auth resolution.

Audit C-02. The pre-fix `_find_by_token` bcrypt-scanned every row in
participants where auth_token_hash IS NOT NULL on every authenticate()
call -- O(N) auth path with bcrypt's slow-by-design constant per row.

This module computes a deterministic HMAC-SHA256 over the plaintext
token using SACP_AUTH_LOOKUP_KEY. Stored alongside the bcrypt hash in
participants.auth_token_lookup, indexed, queried first. The bcrypt
verify still runs after the lookup matches a row, so a leaked HMAC key
alone does not impersonate -- it only narrows the bcrypt-scan target.

Why a separate key (not SACP_ENCRYPTION_KEY): different threat models.
Encryption key rotates may break ciphertext readability across rows;
the lookup key only affects forward-resolution. Different rotation
cadence + audit isolation justify a separate secret.
"""

from __future__ import annotations

import hashlib
import hmac
import os


def compute_token_lookup(token: str) -> str:
    """HMAC-SHA256(SACP_AUTH_LOOKUP_KEY, token) as hex.

    Raises RuntimeError if the env var is unset -- the V16 startup
    validator should refuse to bind ports before this is reached.
    """
    key = os.environ.get("SACP_AUTH_LOOKUP_KEY")
    if not key:
        raise RuntimeError(
            "SACP_AUTH_LOOKUP_KEY must be set (V16 validator should have caught this)"
        )
    return hmac.new(key.encode(), token.encode(), hashlib.sha256).hexdigest()
