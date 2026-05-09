# SPDX-License-Identifier: AGPL-3.0-or-later

"""V16 startup-validator tests for spec 019 (network-layer rate limiting).

Five new SACP_NETWORK_RATELIMIT_* env vars per spec 019 FR-013. Each
validator follows the spec-014 pattern: unset = no-op (or default-applied),
set-but-bad = ValidationFailure with the var name and a human-readable
reason. One cross-validator pair: SACP_NETWORK_RATELIMIT_RPM is required
when SACP_NETWORK_RATELIMIT_ENABLED=true (the limiter requires a budget
to be useful).
"""

from __future__ import annotations

from src.config import validators

# ---------------------------------------------------------------------------
# SACP_NETWORK_RATELIMIT_ENABLED
# ---------------------------------------------------------------------------


def test_enabled_unset_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_NETWORK_RATELIMIT_ENABLED", raising=False)
    assert validators.validate_network_ratelimit_enabled() is None


def test_enabled_true_passes(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "true")
    assert validators.validate_network_ratelimit_enabled() is None


def test_enabled_false_passes(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "false")
    assert validators.validate_network_ratelimit_enabled() is None


def test_enabled_one_zero_pass(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "1")
    assert validators.validate_network_ratelimit_enabled() is None
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "0")
    assert validators.validate_network_ratelimit_enabled() is None


def test_enabled_case_insensitive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "TRUE")
    assert validators.validate_network_ratelimit_enabled() is None
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "False")
    assert validators.validate_network_ratelimit_enabled() is None


def test_enabled_invalid_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "yes")
    failure = validators.validate_network_ratelimit_enabled()
    assert failure is not None
    assert failure.var_name == "SACP_NETWORK_RATELIMIT_ENABLED"


# ---------------------------------------------------------------------------
# SACP_NETWORK_RATELIMIT_RPM
# ---------------------------------------------------------------------------


def test_rpm_unset_disabled_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_NETWORK_RATELIMIT_ENABLED", raising=False)
    monkeypatch.delenv("SACP_NETWORK_RATELIMIT_RPM", raising=False)
    assert validators.validate_network_ratelimit_rpm() is None


def test_rpm_in_range_passes(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_RPM", "60")
    assert validators.validate_network_ratelimit_rpm() is None


def test_rpm_lower_bound_inclusive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_RPM", "1")
    assert validators.validate_network_ratelimit_rpm() is None


def test_rpm_upper_bound_inclusive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_RPM", "6000")
    assert validators.validate_network_ratelimit_rpm() is None


def test_rpm_below_range_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_RPM", "0")
    failure = validators.validate_network_ratelimit_rpm()
    assert failure is not None
    assert failure.var_name == "SACP_NETWORK_RATELIMIT_RPM"
    assert "must be in [1, 6000]" in failure.reason


def test_rpm_above_range_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_RPM", "6001")
    failure = validators.validate_network_ratelimit_rpm()
    assert failure is not None
    assert failure.var_name == "SACP_NETWORK_RATELIMIT_RPM"


def test_rpm_non_integer_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_RPM", "sixty")
    failure = validators.validate_network_ratelimit_rpm()
    assert failure is not None
    assert "must be integer" in failure.reason


def test_rpm_required_when_enabled(monkeypatch) -> None:
    """Cross-validator: _ENABLED=true with _RPM unset is a refuse-to-bind."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "true")
    monkeypatch.delenv("SACP_NETWORK_RATELIMIT_RPM", raising=False)
    failure = validators.validate_network_ratelimit_rpm()
    assert failure is not None
    assert failure.var_name == "SACP_NETWORK_RATELIMIT_RPM"
    assert "SACP_NETWORK_RATELIMIT_ENABLED=true" in failure.reason


def test_rpm_required_when_enabled_is_one(monkeypatch) -> None:
    """ENABLED=1 (boolean alias) also triggers the cross-validator."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "1")
    monkeypatch.delenv("SACP_NETWORK_RATELIMIT_RPM", raising=False)
    failure = validators.validate_network_ratelimit_rpm()
    assert failure is not None
    assert failure.var_name == "SACP_NETWORK_RATELIMIT_RPM"


# ---------------------------------------------------------------------------
# SACP_NETWORK_RATELIMIT_BURST
# ---------------------------------------------------------------------------


def test_burst_unset_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_NETWORK_RATELIMIT_BURST", raising=False)
    assert validators.validate_network_ratelimit_burst() is None


def test_burst_in_range_passes(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_BURST", "15")
    assert validators.validate_network_ratelimit_burst() is None


def test_burst_lower_bound_inclusive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_BURST", "1")
    assert validators.validate_network_ratelimit_burst() is None


def test_burst_upper_bound_inclusive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_BURST", "10000")
    assert validators.validate_network_ratelimit_burst() is None


def test_burst_below_range_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_BURST", "0")
    failure = validators.validate_network_ratelimit_burst()
    assert failure is not None
    assert failure.var_name == "SACP_NETWORK_RATELIMIT_BURST"
    assert "must be in [1, 10000]" in failure.reason


def test_burst_above_range_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_BURST", "10001")
    failure = validators.validate_network_ratelimit_burst()
    assert failure is not None


def test_burst_non_integer_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_BURST", "fifteen")
    failure = validators.validate_network_ratelimit_burst()
    assert failure is not None
    assert "must be integer" in failure.reason


# ---------------------------------------------------------------------------
# SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS
# ---------------------------------------------------------------------------


def test_trust_forwarded_headers_unset_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS", raising=False)
    assert validators.validate_network_ratelimit_trust_forwarded_headers() is None


def test_trust_forwarded_headers_true_passes(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS", "true")
    assert validators.validate_network_ratelimit_trust_forwarded_headers() is None


def test_trust_forwarded_headers_false_passes(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS", "false")
    assert validators.validate_network_ratelimit_trust_forwarded_headers() is None


def test_trust_forwarded_headers_case_insensitive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS", "TRUE")
    assert validators.validate_network_ratelimit_trust_forwarded_headers() is None


def test_trust_forwarded_headers_invalid_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS", "maybe")
    failure = validators.validate_network_ratelimit_trust_forwarded_headers()
    assert failure is not None
    assert failure.var_name == "SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS"


# ---------------------------------------------------------------------------
# SACP_NETWORK_RATELIMIT_MAX_KEYS
# ---------------------------------------------------------------------------


def test_max_keys_unset_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", raising=False)
    assert validators.validate_network_ratelimit_max_keys() is None


def test_max_keys_in_range_passes(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", "100000")
    assert validators.validate_network_ratelimit_max_keys() is None


def test_max_keys_lower_bound_inclusive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", "1024")
    assert validators.validate_network_ratelimit_max_keys() is None


def test_max_keys_upper_bound_inclusive(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", "1000000")
    assert validators.validate_network_ratelimit_max_keys() is None


def test_max_keys_below_range_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", "1023")
    failure = validators.validate_network_ratelimit_max_keys()
    assert failure is not None
    assert failure.var_name == "SACP_NETWORK_RATELIMIT_MAX_KEYS"
    assert "must be in [1024, 1_000_000]" in failure.reason


def test_max_keys_above_range_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", "1000001")
    failure = validators.validate_network_ratelimit_max_keys()
    assert failure is not None


def test_max_keys_non_integer_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", "many")
    failure = validators.validate_network_ratelimit_max_keys()
    assert failure is not None
    assert "must be integer" in failure.reason


# ---------------------------------------------------------------------------
# Tuple registration (V16 contract)
# ---------------------------------------------------------------------------


def test_all_five_validators_registered_in_tuple() -> None:
    """V16 contract: validators only fire if registered in VALIDATORS."""
    registered = {v.__name__ for v in validators.VALIDATORS}
    expected = {
        "validate_network_ratelimit_enabled",
        "validate_network_ratelimit_rpm",
        "validate_network_ratelimit_burst",
        "validate_network_ratelimit_trust_forwarded_headers",
        "validate_network_ratelimit_max_keys",
    }
    missing = expected - registered
    assert not missing, f"validators not registered in VALIDATORS tuple: {sorted(missing)}"
