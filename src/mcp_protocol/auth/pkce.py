# SPDX-License-Identifier: AGPL-3.0-or-later
"""PKCE S256 code-verifier / challenge primitives. Spec 030 Phase 4 FR-071."""

from __future__ import annotations

import base64
import hashlib
import secrets


def generate_code_verifier() -> str:
    """Return a 256-bit URL-safe base64 code verifier."""
    raw = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def compute_challenge(verifier: str) -> str:
    """Return SHA-256(verifier) encoded as base64url without padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_challenge(verifier: str, stored_challenge: str) -> bool:
    """Return True iff SHA-256(verifier) matches the stored S256 challenge."""
    return secrets.compare_digest(compute_challenge(verifier), stored_challenge)
