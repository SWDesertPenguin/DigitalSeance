# SPDX-License-Identifier: AGPL-3.0-or-later

"""Single-use verification + reset code primitives for spec 023.

Generates 16-character Crockford base32 codes via
:func:`secrets.token_bytes` (10 bytes -> ~80 bits of entropy ->
exactly 16 base32 characters before padding) and HMAC-SHA256-hashes
them with ``SACP_AUTH_LOOKUP_KEY`` for durable storage in
``admin_audit_log`` rows. Plaintext codes pass through the email
transport once and are never persisted; only the HMAC hash form
appears in durable state.

The factory entry points (:func:`make_verification_code`,
:func:`make_reset_code`, :func:`make_email_change_code`) bake the
purpose-specific TTL into the returned :class:`AccountCode` so the
caller emits the code via the email transport and writes the audit
row in one step. The audit-log lookup primitive (:func:`hash_code`)
is exposed separately so the consume-side handler can re-hash a
submitted plaintext and look up the matching ``_emitted`` row.

See ``specs/023-user-accounts/contracts/codes.md`` for the full
contract and ``specs/023-user-accounts/research.md`` §3 for the
audit-log-only persistence rationale.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from base64 import b32encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

# Crockford base32 alphabet drops visually ambiguous I, L, O, U from the
# standard b32 alphabet so codes stay readable on phone screens. The
# remap table translates the six standard-b32-only characters that
# don't appear in Crockford to a deterministic non-ambiguous substitute.
_STANDARD_B32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TRANSLATE_TABLE = str.maketrans(_STANDARD_B32_ALPHABET, _CROCKFORD_ALPHABET)

CodePurpose = Literal["verification", "password_reset", "email_change"]

# TTLs per spec FR-004 + clarify Q4 + contracts/codes.md.
_TTL_VERIFICATION = timedelta(hours=24)
_TTL_PASSWORD_RESET = timedelta(minutes=30)
_TTL_EMAIL_CHANGE = timedelta(hours=24)

# Code length in characters. 10 bytes b32-encodes to 16 chars + padding;
# we drop the padding and assert the length downstream.
_CODE_LENGTH = 16


@dataclass(frozen=True)
class AccountCode:
    """One generated verification / reset / email-change code.

    The ``plaintext`` field exits this object exactly once — it is
    handed to the email transport's ``send`` call and then dropped.
    The ``hash`` and ``expires_at`` fields are what gets written to
    the ``admin_audit_log`` ``_emitted`` row; the consume-side handler
    re-hashes a submitted plaintext and looks up the row by
    ``code_hash``.
    """

    plaintext: str
    hash: str
    purpose: CodePurpose
    expires_at: datetime


def generate_code() -> str:
    """Return a 16-character Crockford base32 code with ~80 bits of entropy.

    10 random bytes (80 bits) base32-encode to exactly 16 characters
    before padding. We strip padding (``=``) and translate the
    standard-b32 alphabet to Crockford so the visually ambiguous
    characters drop out.
    """
    raw = secrets.token_bytes(10)
    encoded = b32encode(raw).decode("ascii").rstrip("=")
    code = encoded[:_CODE_LENGTH].translate(_TRANSLATE_TABLE)
    if len(code) != _CODE_LENGTH:
        # Belt-and-braces: 10 bytes always produces 16 chars before padding.
        # If the shape ever drifts (alphabet remap changes, library bug)
        # we want loud failure, not a short code that bypasses the
        # contracts/codes.md length assertion downstream.
        raise RuntimeError(f"code generation produced {len(code)} chars, expected {_CODE_LENGTH}")
    return code


def _normalize_input(plaintext: str) -> str:
    """Crockford-style ambiguity-normalize input then uppercase.

    Per contracts/codes.md: input is case-insensitive; ``I`` and ``L``
    are coerced to ``1``; ``O`` is coerced to ``0``. Generation never
    emits these characters (the alphabet drops them) so the
    normalization is purely tolerance for human typing.
    """
    return plaintext.upper().translate(str.maketrans({"I": "1", "L": "1", "O": "0"}))


def hash_code(plaintext: str) -> str:
    """Return the HMAC-SHA256 hex digest of the normalized plaintext.

    Keyed by ``SACP_AUTH_LOOKUP_KEY``. The same secret backs spec 002's
    participant-token lookup index — sharing it keeps the env var count
    flat and concentrates the rotation surface.
    """
    key = os.environ.get("SACP_AUTH_LOOKUP_KEY", "")
    if not key:
        raise RuntimeError(
            "SACP_AUTH_LOOKUP_KEY is required to hash account codes; "
            "the V16 validator should have rejected an empty value at startup."
        )
    digest = hmac.new(
        key.encode("utf-8"),
        _normalize_input(plaintext).encode("ascii"),
        hashlib.sha256,
    )
    return digest.hexdigest()


def _now_utc() -> datetime:
    """Return ``datetime.now(timezone.utc)`` (helper hook for tests)."""
    return datetime.now(UTC)


def _make_code(purpose: CodePurpose, ttl: timedelta) -> AccountCode:
    plaintext = generate_code()
    return AccountCode(
        plaintext=plaintext,
        hash=hash_code(plaintext),
        purpose=purpose,
        expires_at=_now_utc() + ttl,
    )


def make_verification_code() -> AccountCode:
    """Return a 24h-TTL email-verification code (FR-004)."""
    return _make_code("verification", _TTL_VERIFICATION)


def make_reset_code() -> AccountCode:
    """Return a 30min-TTL password-reset code (FR-004 + clarify Q4)."""
    return _make_code("password_reset", _TTL_PASSWORD_RESET)


def make_email_change_code() -> AccountCode:
    """Return a 24h-TTL email-change verification code (FR-007)."""
    return _make_code("email_change", _TTL_EMAIL_CHANGE)
