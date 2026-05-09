# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 029 V16 validator unit tests (T003 of tasks.md).

Covers each of the three new SACP_* validators per spec 029 FR-017 and
contracts/audit-log-endpoint.md:

- SACP_AUDIT_VIEWER_ENABLED
- SACP_AUDIT_VIEWER_PAGE_SIZE
- SACP_AUDIT_VIEWER_RETENTION_DAYS

Each validator: valid value passes (returns None); out-of-range value
returns a ValidationFailure naming the offending var; empty handled per
the var's allowed-empty rule. Aggregate test confirms registration in the
VALIDATORS tuple so ConfigValidationError fires at startup on misconfig.
"""

from __future__ import annotations

import pytest

from src.config import validators


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the three spec-029 vars unset."""
    for var in (
        "SACP_AUDIT_VIEWER_ENABLED",
        "SACP_AUDIT_VIEWER_PAGE_SIZE",
        "SACP_AUDIT_VIEWER_RETENTION_DAYS",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# SACP_AUDIT_VIEWER_ENABLED
# ---------------------------------------------------------------------------


def test_audit_viewer_enabled_unset_passes() -> None:
    assert validators.validate_audit_viewer_enabled() is None


def test_audit_viewer_enabled_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_ENABLED", "")
    assert validators.validate_audit_viewer_enabled() is None


@pytest.mark.parametrize("value", ["true", "false", "TRUE", "False", "1", "0"])
def test_audit_viewer_enabled_valid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_ENABLED", value)
    assert validators.validate_audit_viewer_enabled() is None


@pytest.mark.parametrize("value", ["yes", "no", "on", "off", "2", "TruE-ish"])
def test_audit_viewer_enabled_invalid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_ENABLED", value)
    failure = validators.validate_audit_viewer_enabled()
    assert failure is not None
    assert failure.var_name == "SACP_AUDIT_VIEWER_ENABLED"


# ---------------------------------------------------------------------------
# SACP_AUDIT_VIEWER_PAGE_SIZE
# ---------------------------------------------------------------------------


def test_audit_viewer_page_size_unset_passes() -> None:
    assert validators.validate_audit_viewer_page_size() is None


def test_audit_viewer_page_size_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_PAGE_SIZE", "")
    assert validators.validate_audit_viewer_page_size() is None


@pytest.mark.parametrize("value", ["10", "50", "100", "499", "500"])
def test_audit_viewer_page_size_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_PAGE_SIZE", value)
    assert validators.validate_audit_viewer_page_size() is None


@pytest.mark.parametrize("value", ["0", "9", "-1", "501", "10000"])
def test_audit_viewer_page_size_out_of_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_PAGE_SIZE", value)
    failure = validators.validate_audit_viewer_page_size()
    assert failure is not None
    assert failure.var_name == "SACP_AUDIT_VIEWER_PAGE_SIZE"


@pytest.mark.parametrize("value", ["abc", "1.5", "fifty"])
def test_audit_viewer_page_size_non_integer(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_PAGE_SIZE", value)
    failure = validators.validate_audit_viewer_page_size()
    assert failure is not None
    assert "integer" in failure.reason


# ---------------------------------------------------------------------------
# SACP_AUDIT_VIEWER_RETENTION_DAYS
# ---------------------------------------------------------------------------


def test_audit_viewer_retention_unset_passes() -> None:
    assert validators.validate_audit_viewer_retention_days() is None


def test_audit_viewer_retention_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty string is the documented default — no retention WHERE clause."""
    monkeypatch.setenv("SACP_AUDIT_VIEWER_RETENTION_DAYS", "")
    assert validators.validate_audit_viewer_retention_days() is None


@pytest.mark.parametrize("value", ["1", "30", "90", "365", "36500"])
def test_audit_viewer_retention_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_RETENTION_DAYS", value)
    assert validators.validate_audit_viewer_retention_days() is None


@pytest.mark.parametrize("value", ["0", "-1", "36501", "999999"])
def test_audit_viewer_retention_out_of_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_RETENTION_DAYS", value)
    failure = validators.validate_audit_viewer_retention_days()
    assert failure is not None
    assert failure.var_name == "SACP_AUDIT_VIEWER_RETENTION_DAYS"


@pytest.mark.parametrize("value", ["abc", "1.5", "thirty"])
def test_audit_viewer_retention_non_integer(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_RETENTION_DAYS", value)
    failure = validators.validate_audit_viewer_retention_days()
    assert failure is not None
    assert "integer" in failure.reason


# ---------------------------------------------------------------------------
# Aggregate: all three validators registered in VALIDATORS tuple
# ---------------------------------------------------------------------------


def test_all_three_validators_registered() -> None:
    """T003 sanity: each spec-029 validator is in the VALIDATORS tuple."""
    names = {v.__name__ for v in validators.VALIDATORS}
    assert "validate_audit_viewer_enabled" in names
    assert "validate_audit_viewer_page_size" in names
    assert "validate_audit_viewer_retention_days" in names
