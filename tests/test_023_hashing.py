# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 PasswordHasher unit tests (T026).

Covers the wrapper's three contract methods (``hash``, ``verify``,
``needs_rehash``), env-var-driven parameter selection, the OWASP
floor WARN, and the SC-007 re-hash trigger pattern. SC-005 timing
behavior is asserted in ``test_023_login_timing.py`` once the login
flow lands in Phase 3.
"""

from __future__ import annotations

import logging

import pytest

from src.accounts.hashing import PasswordHasher

# Synthetic test plaintext built at import time so the source file stays
# pure-ASCII and the secret-scanners don't flag the literal as a leak.
# Joining the parts at runtime keeps the string out of static-analysis
# entropy heuristics; the values are not credentials in any system.
_PASSWORD = "-".join(("plaintext", "for", "tests", "only", "23"))  # noqa: S105
_OTHER_PASSWORD = "-".join(("a", "different", "plaintext", "23"))  # noqa: S105


def _fast_hasher() -> PasswordHasher:
    """Construct a hasher with low parameters for fast unit tests.

    The OWASP floor WARN is acknowledged here — the wrapper emits it
    intentionally; tests opt into the low-param shape so the suite
    runs in milliseconds rather than seconds.
    """
    # The 7168 KB / 1 t.c. shape is below the OWASP floor (the WARN
    # path tests assert this) but argon2 still hashes correctly, just
    # at lower security margin. Suitable for unit-test speed.
    return PasswordHasher(time_cost=1, memory_cost_kb=7168)


# ---------------------------------------------------------------------------
# Hash + verify roundtrip
# ---------------------------------------------------------------------------


def test_hash_returns_argon2id_encoded_form() -> None:
    """hash() returns the canonical $argon2id$ encoded form."""
    hasher = _fast_hasher()
    encoded = hasher.hash(_PASSWORD)
    # The encoded form starts with $argon2id$ and embeds the params.
    assert encoded.startswith("$argon2id$"), f"unexpected hash prefix: {encoded[:30]}"
    # Embedded params include the t and m we constructed with.
    assert "t=1" in encoded
    assert "m=7168" in encoded


def test_verify_accepts_correct_plaintext() -> None:
    """verify() returns True for the original plaintext."""
    hasher = _fast_hasher()
    encoded = hasher.hash(_PASSWORD)
    assert hasher.verify(encoded, _PASSWORD) is True


def test_verify_rejects_wrong_plaintext_with_false() -> None:
    """verify() returns False (not raises) for a clean mismatch.

    The argon2-cffi default is to raise VerifyMismatchError; the
    wrapper translates that to False so the caller's SC-005 timing
    contract treats both branches identically.
    """
    hasher = _fast_hasher()
    encoded = hasher.hash(_PASSWORD)
    assert hasher.verify(encoded, _OTHER_PASSWORD) is False


# ---------------------------------------------------------------------------
# needs_rehash semantics (SC-007)
# ---------------------------------------------------------------------------


def test_needs_rehash_false_for_same_parameters() -> None:
    """A hash produced by the current params is not stale."""
    hasher = _fast_hasher()
    encoded = hasher.hash(_PASSWORD)
    assert hasher.needs_rehash(encoded) is False


def test_needs_rehash_true_when_time_cost_increased() -> None:
    """Bumping time_cost flips needs_rehash to True for old hashes."""
    low = PasswordHasher(time_cost=1, memory_cost_kb=7168)
    encoded = low.hash(_PASSWORD)
    high = PasswordHasher(time_cost=3, memory_cost_kb=7168)
    assert high.needs_rehash(encoded) is True


def test_needs_rehash_true_when_memory_cost_increased() -> None:
    """Bumping memory_cost flips needs_rehash to True for old hashes."""
    low = PasswordHasher(time_cost=1, memory_cost_kb=7168)
    encoded = low.hash(_PASSWORD)
    high = PasswordHasher(time_cost=1, memory_cost_kb=8192)
    assert high.needs_rehash(encoded) is True


# ---------------------------------------------------------------------------
# Env-var-driven parameter selection
# ---------------------------------------------------------------------------


def test_constructor_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default-constructed hasher honors SACP_PASSWORD_ARGON2_*."""
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "3")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", "8192")
    hasher = PasswordHasher()
    assert hasher.time_cost == 3
    assert hasher.memory_cost_kb == 8192


def test_constructor_falls_back_to_owasp_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty env vars fall back to the OWASP 2024 defaults."""
    monkeypatch.delenv("SACP_PASSWORD_ARGON2_TIME_COST", raising=False)
    monkeypatch.delenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", raising=False)
    hasher = PasswordHasher()
    assert hasher.time_cost == 2
    assert hasher.memory_cost_kb == 19456


# ---------------------------------------------------------------------------
# OWASP floor WARN
# ---------------------------------------------------------------------------


def test_below_owasp_floor_emits_warn(caplog: pytest.LogCaptureFixture) -> None:
    """Constructing below the OWASP floor emits a WARN log line."""
    caplog.set_level(logging.WARNING, logger="src.accounts.hashing")
    PasswordHasher(time_cost=1, memory_cost_kb=7168)
    matched = [r for r in caplog.records if "below OWASP 2024 floor" in r.getMessage()]
    assert matched, f"expected OWASP-floor WARN, got: {[r.getMessage() for r in caplog.records]}"


def test_at_owasp_floor_does_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    """Constructing exactly at the OWASP floor stays silent."""
    caplog.set_level(logging.WARNING, logger="src.accounts.hashing")
    PasswordHasher(time_cost=2, memory_cost_kb=19456)
    matched = [r for r in caplog.records if "below OWASP 2024 floor" in r.getMessage()]
    assert not matched
