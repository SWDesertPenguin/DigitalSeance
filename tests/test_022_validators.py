# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 V16 validator unit tests (T003 of tasks.md).

Covers each of the three new SACP_* validators per spec 022 FR-016 and
contracts/detection-events-endpoint.md:

- SACP_DETECTION_HISTORY_ENABLED
- SACP_DETECTION_HISTORY_MAX_EVENTS
- SACP_DETECTION_HISTORY_RETENTION_DAYS

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
    """Each test starts with the three spec-022 vars unset."""
    for var in (
        "SACP_DETECTION_HISTORY_ENABLED",
        "SACP_DETECTION_HISTORY_MAX_EVENTS",
        "SACP_DETECTION_HISTORY_RETENTION_DAYS",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# SACP_DETECTION_HISTORY_ENABLED
# ---------------------------------------------------------------------------


def test_detection_history_enabled_unset_passes() -> None:
    assert validators.validate_detection_history_enabled() is None


def test_detection_history_enabled_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_ENABLED", "")
    assert validators.validate_detection_history_enabled() is None


@pytest.mark.parametrize("value", ["true", "false", "TRUE", "False", "1", "0"])
def test_detection_history_enabled_valid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_ENABLED", value)
    assert validators.validate_detection_history_enabled() is None


@pytest.mark.parametrize("value", ["yes", "no", "on", "off", "2", "TruE-ish"])
def test_detection_history_enabled_invalid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_ENABLED", value)
    failure = validators.validate_detection_history_enabled()
    assert failure is not None
    assert failure.var_name == "SACP_DETECTION_HISTORY_ENABLED"


# ---------------------------------------------------------------------------
# SACP_DETECTION_HISTORY_MAX_EVENTS
# ---------------------------------------------------------------------------


def test_detection_history_max_events_unset_passes() -> None:
    assert validators.validate_detection_history_max_events() is None


def test_detection_history_max_events_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty string is the documented default — no LIMIT clause."""
    monkeypatch.setenv("SACP_DETECTION_HISTORY_MAX_EVENTS", "")
    assert validators.validate_detection_history_max_events() is None


@pytest.mark.parametrize("value", ["1", "50", "1000", "99999", "100000"])
def test_detection_history_max_events_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_MAX_EVENTS", value)
    assert validators.validate_detection_history_max_events() is None


@pytest.mark.parametrize("value", ["0", "-1", "100001", "999999"])
def test_detection_history_max_events_out_of_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_MAX_EVENTS", value)
    failure = validators.validate_detection_history_max_events()
    assert failure is not None
    assert failure.var_name == "SACP_DETECTION_HISTORY_MAX_EVENTS"


@pytest.mark.parametrize("value", ["abc", "1.5", "fifty"])
def test_detection_history_max_events_non_integer(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_MAX_EVENTS", value)
    failure = validators.validate_detection_history_max_events()
    assert failure is not None
    assert "integer" in failure.reason


# ---------------------------------------------------------------------------
# SACP_DETECTION_HISTORY_RETENTION_DAYS
# ---------------------------------------------------------------------------


def test_detection_history_retention_unset_passes() -> None:
    assert validators.validate_detection_history_retention_days() is None


def test_detection_history_retention_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty string is the documented default — no retention WHERE clause."""
    monkeypatch.setenv("SACP_DETECTION_HISTORY_RETENTION_DAYS", "")
    assert validators.validate_detection_history_retention_days() is None


@pytest.mark.parametrize("value", ["1", "30", "90", "365", "36500"])
def test_detection_history_retention_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_RETENTION_DAYS", value)
    assert validators.validate_detection_history_retention_days() is None


@pytest.mark.parametrize("value", ["0", "-1", "36501", "999999"])
def test_detection_history_retention_out_of_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_RETENTION_DAYS", value)
    failure = validators.validate_detection_history_retention_days()
    assert failure is not None
    assert failure.var_name == "SACP_DETECTION_HISTORY_RETENTION_DAYS"


@pytest.mark.parametrize("value", ["abc", "1.5", "thirty"])
def test_detection_history_retention_non_integer(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_RETENTION_DAYS", value)
    failure = validators.validate_detection_history_retention_days()
    assert failure is not None
    assert "integer" in failure.reason


# ---------------------------------------------------------------------------
# Aggregate: all three validators registered in VALIDATORS tuple
# ---------------------------------------------------------------------------


def test_all_three_validators_registered() -> None:
    """T003 sanity: each spec-022 validator is in the VALIDATORS tuple."""
    names = {v.__name__ for v in validators.VALIDATORS}
    assert "validate_detection_history_enabled" in names
    assert "validate_detection_history_max_events" in names
    assert "validate_detection_history_retention_days" in names
