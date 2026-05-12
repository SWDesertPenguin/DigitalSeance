# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 027 V16 validator unit tests (T006 of tasks.md).

Covers each of the four new SACP_STANDBY_* validators per spec 027 §FR-028
and `docs/env-vars.md`:

- SACP_STANDBY_DEFAULT_WAIT_MODE
- SACP_STANDBY_FILLER_DETECTION_TURNS
- SACP_STANDBY_PIVOT_TIMEOUT_SECONDS
- SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION

Each validator: valid value passes (returns None); out-of-range value
returns a ValidationFailure naming the offending var; empty handled per
the var's allowed-empty rule.
"""

from __future__ import annotations

import pytest

from src.config import validators


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the four spec-027 vars unset."""
    for var in (
        "SACP_STANDBY_DEFAULT_WAIT_MODE",
        "SACP_STANDBY_FILLER_DETECTION_TURNS",
        "SACP_STANDBY_PIVOT_TIMEOUT_SECONDS",
        "SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION",
    ):
        monkeypatch.delenv(var, raising=False)


def test_default_wait_mode_unset_returns_none() -> None:
    assert validators.validate_standby_default_wait_mode() is None


@pytest.mark.parametrize("value", ["wait_for_human", "always"])
def test_default_wait_mode_valid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_STANDBY_DEFAULT_WAIT_MODE", value)
    assert validators.validate_standby_default_wait_mode() is None


@pytest.mark.parametrize("value", ["Wait_For_Human", "off", "", " "])
def test_default_wait_mode_invalid_or_empty(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_STANDBY_DEFAULT_WAIT_MODE", value)
    failure = validators.validate_standby_default_wait_mode()
    if value.strip() == "":
        assert failure is None
    else:
        assert failure is not None
        assert failure.var_name == "SACP_STANDBY_DEFAULT_WAIT_MODE"


def test_filler_detection_turns_unset_returns_none() -> None:
    assert validators.validate_standby_filler_detection_turns() is None


@pytest.mark.parametrize("value", ["2", "5", "100"])
def test_filler_detection_turns_valid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_STANDBY_FILLER_DETECTION_TURNS", value)
    assert validators.validate_standby_filler_detection_turns() is None


@pytest.mark.parametrize("value", ["1", "0", "101", "abc"])
def test_filler_detection_turns_invalid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_STANDBY_FILLER_DETECTION_TURNS", value)
    failure = validators.validate_standby_filler_detection_turns()
    assert failure is not None
    assert failure.var_name == "SACP_STANDBY_FILLER_DETECTION_TURNS"


def test_pivot_timeout_seconds_unset_returns_none() -> None:
    assert validators.validate_standby_pivot_timeout_seconds() is None


@pytest.mark.parametrize("value", ["60", "600", "86400"])
def test_pivot_timeout_seconds_valid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_STANDBY_PIVOT_TIMEOUT_SECONDS", value)
    assert validators.validate_standby_pivot_timeout_seconds() is None


@pytest.mark.parametrize("value", ["59", "0", "86401", "xyz"])
def test_pivot_timeout_seconds_invalid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_STANDBY_PIVOT_TIMEOUT_SECONDS", value)
    failure = validators.validate_standby_pivot_timeout_seconds()
    assert failure is not None
    assert failure.var_name == "SACP_STANDBY_PIVOT_TIMEOUT_SECONDS"


def test_pivot_rate_cap_unset_returns_none() -> None:
    assert validators.validate_standby_pivot_rate_cap_per_session() is None


@pytest.mark.parametrize("value", ["0", "1", "100"])
def test_pivot_rate_cap_valid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION", value)
    assert validators.validate_standby_pivot_rate_cap_per_session() is None


@pytest.mark.parametrize("value", ["-1", "101", "not_int"])
def test_pivot_rate_cap_invalid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION", value)
    failure = validators.validate_standby_pivot_rate_cap_per_session()
    assert failure is not None
    assert failure.var_name == "SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION"


def test_all_four_registered_in_validators_tuple() -> None:
    """Every new validator must appear in the VALIDATORS tuple."""
    fn_names = {fn.__name__ for fn in validators.VALIDATORS}
    assert "validate_standby_default_wait_mode" in fn_names
    assert "validate_standby_filler_detection_turns" in fn_names
    assert "validate_standby_pivot_timeout_seconds" in fn_names
    assert "validate_standby_pivot_rate_cap_per_session" in fn_names
