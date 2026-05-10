# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 code-generation + HMAC-hashing unit tests (T027).

Covers ``generate_code`` (length + alphabet + entropy spot-check),
``hash_code`` (HMAC-SHA256 keyed by SACP_AUTH_LOOKUP_KEY +
case-insensitive normalization + Crockford ambiguity remap), and the
three factory entry points (``make_verification_code``,
``make_reset_code``, ``make_email_change_code``) with their
purpose-specific TTLs from FR-004 + clarify Q4. The single-use
audit-log persistence semantics are exercised in
``test_023_account_create.py`` once the service-layer flow lands.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta

import pytest

from src.accounts import codes as codes_module
from src.accounts.codes import (
    generate_code,
    hash_code,
    make_email_change_code,
    make_reset_code,
    make_verification_code,
)

_CROCKFORD_ALPHABET_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{16}$")


# ---------------------------------------------------------------------------
# generate_code shape
# ---------------------------------------------------------------------------


def test_generated_code_is_16_chars() -> None:
    assert len(generate_code()) == 16


def test_generated_code_uses_crockford_alphabet() -> None:
    """Generated codes only use the Crockford alphabet (drops I, L, O, U)."""
    for _ in range(50):
        code = generate_code()
        assert _CROCKFORD_ALPHABET_RE.match(code), f"non-crockford char in {code!r}"


def test_generated_codes_are_distinct_across_calls() -> None:
    """80 bits of entropy makes collisions astronomically unlikely.

    Spot-check: 100 codes are all distinct.
    """
    samples = {generate_code() for _ in range(100)}
    assert len(samples) == 100


# ---------------------------------------------------------------------------
# hash_code semantics
# ---------------------------------------------------------------------------


def test_hash_code_produces_hmac_sha256_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    """hash_code returns the HMAC-SHA256 hex digest under SACP_AUTH_LOOKUP_KEY."""
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    plaintext = "ABCDEFGHJKMNPQRS"
    expected = hmac.new(
        b"test-key-for-codes-do-not-use-in-prod",
        plaintext.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    assert hash_code(plaintext) == expected


def test_hash_code_normalizes_lowercase_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lowercase input hashes to the same value as uppercase."""
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    assert hash_code("abcdefghjkmnpqrs") == hash_code("ABCDEFGHJKMNPQRS")


def test_hash_code_normalizes_crockford_ambiguous_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I and L coerce to 1; O coerces to 0 — per contracts/codes.md.

    The generator never emits I/L/O so this normalization is purely
    input tolerance for users typing the code from an email. After
    normalize ``ILOL1010`` becomes ``11011010`` (I->1, L->1, O->0,
    L->1) — the equivalence on the hash side proves both forms collapse
    to the same digest.
    """
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    # ILOL1010 normalizes to 11011010 by the I->1, L->1, O->0 mapping.
    assert hash_code("ILOL1010") == hash_code("11011010")


def test_hash_code_raises_when_lookup_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty SACP_AUTH_LOOKUP_KEY produces a loud RuntimeError."""
    monkeypatch.delenv("SACP_AUTH_LOOKUP_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SACP_AUTH_LOOKUP_KEY"):
        hash_code("ABCDEFGHJKMNPQRS")


# ---------------------------------------------------------------------------
# Factory entry points + TTLs
# ---------------------------------------------------------------------------


def _ttl_seconds(code_expires_at: datetime) -> float:
    """Helper: estimate the TTL of a freshly-minted code."""
    delta = code_expires_at - datetime.now(UTC)
    return delta.total_seconds()


def test_make_verification_code_has_24h_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-004: email verification TTL is 24 hours."""
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    code = make_verification_code()
    target = timedelta(hours=24).total_seconds()
    assert abs(_ttl_seconds(code.expires_at) - target) < 5  # within 5s of "now + 24h"
    assert code.purpose == "verification"


def test_make_reset_code_has_30min_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-004 + clarify Q4: password reset TTL is 30 minutes."""
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    code = make_reset_code()
    target = timedelta(minutes=30).total_seconds()
    assert abs(_ttl_seconds(code.expires_at) - target) < 5
    assert code.purpose == "password_reset"


def test_make_email_change_code_has_24h_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-007: email-change verification TTL is 24 hours."""
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    code = make_email_change_code()
    target = timedelta(hours=24).total_seconds()
    assert abs(_ttl_seconds(code.expires_at) - target) < 5
    assert code.purpose == "email_change"


def test_factory_returns_consistent_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hash field on AccountCode equals hash_code(plaintext)."""
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    code = make_verification_code()
    assert code.hash == hash_code(code.plaintext)


# ---------------------------------------------------------------------------
# Generation guard rail
# ---------------------------------------------------------------------------


def test_generate_code_raises_on_short_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the generator ever emits a non-16-char code, raise loudly."""
    monkeypatch.setattr(codes_module.secrets, "token_bytes", lambda _n: b"\x00" * 5)
    with pytest.raises(RuntimeError, match="code generation produced"):
        generate_code()
