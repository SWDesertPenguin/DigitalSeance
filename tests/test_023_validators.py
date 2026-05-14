# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 V16 validator unit tests (T017 of tasks.md).

Covers each of the seven new SACP_* validators per spec 023 FR-022 and
contracts/env-vars.md:

- SACP_ACCOUNTS_ENABLED
- SACP_PASSWORD_ARGON2_TIME_COST
- SACP_PASSWORD_ARGON2_MEMORY_COST_KB
- SACP_ACCOUNT_SESSION_TTL_HOURS
- SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN
- SACP_EMAIL_TRANSPORT
- SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS

Each validator: valid value passes (returns None); out-of-range value
returns a ValidationFailure naming the offending var; empty handled per
the var's allowed-empty rule. Aggregate test confirms registration in the
VALIDATORS tuple so ConfigValidationError fires at startup on misconfig.

The SACP_EMAIL_TRANSPORT={smtp,ses,sendgrid} reserved-value-passes-
syntactic case is also covered here. The NotImplementedError path lives
in Phase 2 when the adapter factory lands.
"""

from __future__ import annotations

import pytest

from src.config import validators

_SPEC_023_VARS = (
    "SACP_ACCOUNTS_ENABLED",
    "SACP_PASSWORD_ARGON2_TIME_COST",
    "SACP_PASSWORD_ARGON2_MEMORY_COST_KB",
    "SACP_ACCOUNT_SESSION_TTL_HOURS",
    "SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN",
    "SACP_EMAIL_TRANSPORT",
    "SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS",
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the seven spec-023 vars unset."""
    for var in _SPEC_023_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# SACP_ACCOUNTS_ENABLED
# ---------------------------------------------------------------------------


def test_accounts_enabled_unset_passes() -> None:
    assert validators.validate_accounts_enabled() is None


@pytest.mark.parametrize("value", ["0", "1"])
def test_accounts_enabled_valid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", value)
    assert validators.validate_accounts_enabled() is None


@pytest.mark.parametrize("value", ["true", "false", "yes", "no", "2", "-1", ""])
def test_accounts_enabled_invalid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", value)
    failure = validators.validate_accounts_enabled()
    assert failure is not None
    assert failure.var_name == "SACP_ACCOUNTS_ENABLED"


# ---------------------------------------------------------------------------
# SACP_PASSWORD_ARGON2_TIME_COST
# ---------------------------------------------------------------------------


def test_password_argon2_time_cost_unset_passes() -> None:
    assert validators.validate_password_argon2_time_cost() is None


def test_password_argon2_time_cost_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "")
    assert validators.validate_password_argon2_time_cost() is None


@pytest.mark.parametrize("value", ["1", "2", "3", "5", "10"])
def test_password_argon2_time_cost_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", value)
    assert validators.validate_password_argon2_time_cost() is None


@pytest.mark.parametrize("value", ["0", "-1", "11", "100"])
def test_password_argon2_time_cost_out_of_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", value)
    failure = validators.validate_password_argon2_time_cost()
    assert failure is not None
    assert failure.var_name == "SACP_PASSWORD_ARGON2_TIME_COST"


@pytest.mark.parametrize("value", ["abc", "high", "2.5"])
def test_password_argon2_time_cost_non_integer(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", value)
    failure = validators.validate_password_argon2_time_cost()
    assert failure is not None
    assert failure.var_name == "SACP_PASSWORD_ARGON2_TIME_COST"
    assert "integer" in failure.reason


# ---------------------------------------------------------------------------
# SACP_PASSWORD_ARGON2_MEMORY_COST_KB
# ---------------------------------------------------------------------------


def test_password_argon2_memory_cost_kb_unset_passes() -> None:
    assert validators.validate_password_argon2_memory_cost_kb() is None


def test_password_argon2_memory_cost_kb_empty_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", "")
    assert validators.validate_password_argon2_memory_cost_kb() is None


@pytest.mark.parametrize("value", ["7168", "19456", "65536", "1048576"])
def test_password_argon2_memory_cost_kb_in_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", value)
    assert validators.validate_password_argon2_memory_cost_kb() is None


@pytest.mark.parametrize("value", ["0", "1024", "7167", "1048577", "10000000"])
def test_password_argon2_memory_cost_kb_out_of_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", value)
    failure = validators.validate_password_argon2_memory_cost_kb()
    assert failure is not None
    assert failure.var_name == "SACP_PASSWORD_ARGON2_MEMORY_COST_KB"


@pytest.mark.parametrize("value", ["abc", "19456.5"])
def test_password_argon2_memory_cost_kb_non_integer(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", value)
    failure = validators.validate_password_argon2_memory_cost_kb()
    assert failure is not None
    assert failure.var_name == "SACP_PASSWORD_ARGON2_MEMORY_COST_KB"


# ---------------------------------------------------------------------------
# SACP_ACCOUNT_SESSION_TTL_HOURS
# ---------------------------------------------------------------------------


def test_account_session_ttl_hours_unset_passes() -> None:
    assert validators.validate_account_session_ttl_hours() is None


def test_account_session_ttl_hours_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_SESSION_TTL_HOURS", "")
    assert validators.validate_account_session_ttl_hours() is None


@pytest.mark.parametrize("value", ["1", "24", "168", "720", "8760"])
def test_account_session_ttl_hours_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_SESSION_TTL_HOURS", value)
    assert validators.validate_account_session_ttl_hours() is None


@pytest.mark.parametrize("value", ["0", "-1", "8761", "100000"])
def test_account_session_ttl_hours_out_of_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_SESSION_TTL_HOURS", value)
    failure = validators.validate_account_session_ttl_hours()
    assert failure is not None
    assert failure.var_name == "SACP_ACCOUNT_SESSION_TTL_HOURS"


@pytest.mark.parametrize("value", ["forever", "168.5"])
def test_account_session_ttl_hours_non_integer(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_SESSION_TTL_HOURS", value)
    failure = validators.validate_account_session_ttl_hours()
    assert failure is not None
    assert failure.var_name == "SACP_ACCOUNT_SESSION_TTL_HOURS"


# ---------------------------------------------------------------------------
# SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN
# ---------------------------------------------------------------------------


def test_account_rate_limit_per_ip_per_min_unset_passes() -> None:
    assert validators.validate_account_rate_limit_per_ip_per_min() is None


def test_account_rate_limit_per_ip_per_min_empty_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN", "")
    assert validators.validate_account_rate_limit_per_ip_per_min() is None


@pytest.mark.parametrize("value", ["1", "10", "100", "1000"])
def test_account_rate_limit_per_ip_per_min_in_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN", value)
    assert validators.validate_account_rate_limit_per_ip_per_min() is None


@pytest.mark.parametrize("value", ["0", "-1", "1001", "100000"])
def test_account_rate_limit_per_ip_per_min_out_of_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN", value)
    failure = validators.validate_account_rate_limit_per_ip_per_min()
    assert failure is not None
    assert failure.var_name == "SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN"


@pytest.mark.parametrize("value", ["ten", "10.5"])
def test_account_rate_limit_per_ip_per_min_non_integer(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN", value)
    failure = validators.validate_account_rate_limit_per_ip_per_min()
    assert failure is not None
    assert failure.var_name == "SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN"


# ---------------------------------------------------------------------------
# SACP_EMAIL_TRANSPORT
# ---------------------------------------------------------------------------


def test_email_transport_unset_passes() -> None:
    assert validators.validate_email_transport() is None


def test_email_transport_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "")
    assert validators.validate_email_transport() is None


def test_email_transport_noop_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """v1 ships only the noop adapter; it passes V16."""
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "noop")
    assert validators.validate_email_transport() is None


@pytest.mark.parametrize("value", ["smtp", "ses", "sendgrid"])
def test_email_transport_reserved_values_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """smtp/ses/sendgrid are syntactically valid but unimplemented in v1.

    V16 rejects them at startup so the process exits before binding ports
    rather than booting and crashing on first email send. Closes the
    fail-open hole flagged by /speckit.analyze finding 23-F1.
    """
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", value)
    failure = validators.validate_email_transport()
    assert failure is not None
    assert failure.var_name == "SACP_EMAIL_TRANSPORT"
    assert "follow-up" in failure.reason


@pytest.mark.parametrize("value", ["NOOP", "Smtp", "mailgun", "postmark", "any"])
def test_email_transport_out_of_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", value)
    failure = validators.validate_email_transport()
    assert failure is not None
    assert failure.var_name == "SACP_EMAIL_TRANSPORT"


# ---------------------------------------------------------------------------
# SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS
# ---------------------------------------------------------------------------


def test_account_deletion_email_grace_days_unset_passes() -> None:
    assert validators.validate_account_deletion_email_grace_days() is None


def test_account_deletion_email_grace_days_empty_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS", "")
    assert validators.validate_account_deletion_email_grace_days() is None


@pytest.mark.parametrize("value", ["0", "1", "7", "30", "365"])
def test_account_deletion_email_grace_days_in_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Value 0 disables the grace period entirely; 365 is the upper bound."""
    monkeypatch.setenv("SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS", value)
    assert validators.validate_account_deletion_email_grace_days() is None


@pytest.mark.parametrize("value", ["-1", "366", "100000"])
def test_account_deletion_email_grace_days_out_of_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS", value)
    failure = validators.validate_account_deletion_email_grace_days()
    assert failure is not None
    assert failure.var_name == "SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS"


@pytest.mark.parametrize("value", ["seven", "7.5"])
def test_account_deletion_email_grace_days_non_integer(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS", value)
    failure = validators.validate_account_deletion_email_grace_days()
    assert failure is not None
    assert failure.var_name == "SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS"


# ---------------------------------------------------------------------------
# Aggregate: all seven validators registered in VALIDATORS tuple
# ---------------------------------------------------------------------------


def test_all_seven_validators_registered() -> None:
    """T008 sanity: each of the seven new validators is in the VALIDATORS tuple."""
    names = {v.__name__ for v in validators.VALIDATORS}
    assert "validate_accounts_enabled" in names
    assert "validate_password_argon2_time_cost" in names
    assert "validate_password_argon2_memory_cost_kb" in names
    assert "validate_account_session_ttl_hours" in names
    assert "validate_account_rate_limit_per_ip_per_min" in names
    assert "validate_email_transport" in names
    assert "validate_account_deletion_email_grace_days" in names


def test_iter_failures_aggregates_spec_023_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set three of the seven vars out-of-range; iter_failures yields them all."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "yes")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "100")
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "mailgun")
    failures = list(validators.iter_failures())
    var_names = {f.var_name for f in failures}
    assert "SACP_ACCOUNTS_ENABLED" in var_names
    assert "SACP_PASSWORD_ARGON2_TIME_COST" in var_names
    assert "SACP_EMAIL_TRANSPORT" in var_names
