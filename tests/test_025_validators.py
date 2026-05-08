"""Spec 025 V16 validator unit tests (T015 of tasks.md).

Covers each of the five new SACP_* validators per spec 025 FR-024 / FR-025
and contracts/env-vars.md:

- SACP_LENGTH_CAP_DEFAULT_KIND
- SACP_LENGTH_CAP_DEFAULT_SECONDS
- SACP_LENGTH_CAP_DEFAULT_TURNS
- SACP_CONCLUDE_PHASE_TRIGGER_FRACTION
- SACP_CONCLUDE_PHASE_PROMPT_TIER

Each validator: valid value passes (returns None); out-of-range value
returns a ValidationFailure naming the offending var; empty handled per
the var's allowed-empty rule.
"""

from __future__ import annotations

import pytest

from src.config import validators


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the five spec-025 vars unset."""
    for var in (
        "SACP_LENGTH_CAP_DEFAULT_KIND",
        "SACP_LENGTH_CAP_DEFAULT_SECONDS",
        "SACP_LENGTH_CAP_DEFAULT_TURNS",
        "SACP_CONCLUDE_PHASE_TRIGGER_FRACTION",
        "SACP_CONCLUDE_PHASE_PROMPT_TIER",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# SACP_LENGTH_CAP_DEFAULT_KIND
# ---------------------------------------------------------------------------


def test_default_kind_unset_uses_none_default() -> None:
    assert validators.validate_sacp_length_cap_default_kind() is None


@pytest.mark.parametrize("value", ["none", "time", "turns", "both"])
def test_default_kind_valid_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_LENGTH_CAP_DEFAULT_KIND", value)
    assert validators.validate_sacp_length_cap_default_kind() is None


@pytest.mark.parametrize("value", ["", "TIME", "always", "0", "True"])
def test_default_kind_invalid_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_LENGTH_CAP_DEFAULT_KIND", value)
    failure = validators.validate_sacp_length_cap_default_kind()
    assert failure is not None
    assert failure.var_name == "SACP_LENGTH_CAP_DEFAULT_KIND"


# ---------------------------------------------------------------------------
# SACP_LENGTH_CAP_DEFAULT_SECONDS
# ---------------------------------------------------------------------------


def test_default_seconds_unset_passes() -> None:
    assert validators.validate_sacp_length_cap_default_seconds() is None


def test_default_seconds_empty_string_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_LENGTH_CAP_DEFAULT_SECONDS", "")
    assert validators.validate_sacp_length_cap_default_seconds() is None


@pytest.mark.parametrize("value", ["60", "1800", "7200", "2592000"])
def test_default_seconds_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_LENGTH_CAP_DEFAULT_SECONDS", value)
    assert validators.validate_sacp_length_cap_default_seconds() is None


@pytest.mark.parametrize("value", ["59", "0", "-1", "2592001", "999999999"])
def test_default_seconds_out_of_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_LENGTH_CAP_DEFAULT_SECONDS", value)
    failure = validators.validate_sacp_length_cap_default_seconds()
    assert failure is not None
    assert failure.var_name == "SACP_LENGTH_CAP_DEFAULT_SECONDS"


@pytest.mark.parametrize("value", ["abc", "1.5", "minute"])
def test_default_seconds_non_integer(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_LENGTH_CAP_DEFAULT_SECONDS", value)
    failure = validators.validate_sacp_length_cap_default_seconds()
    assert failure is not None
    assert "integer" in failure.reason


# ---------------------------------------------------------------------------
# SACP_LENGTH_CAP_DEFAULT_TURNS
# ---------------------------------------------------------------------------


def test_default_turns_unset_passes() -> None:
    assert validators.validate_sacp_length_cap_default_turns() is None


@pytest.mark.parametrize("value", ["1", "20", "200", "10000"])
def test_default_turns_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_LENGTH_CAP_DEFAULT_TURNS", value)
    assert validators.validate_sacp_length_cap_default_turns() is None


@pytest.mark.parametrize("value", ["0", "-1", "10001", "99999"])
def test_default_turns_out_of_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_LENGTH_CAP_DEFAULT_TURNS", value)
    failure = validators.validate_sacp_length_cap_default_turns()
    assert failure is not None
    assert failure.var_name == "SACP_LENGTH_CAP_DEFAULT_TURNS"


# ---------------------------------------------------------------------------
# SACP_CONCLUDE_PHASE_TRIGGER_FRACTION
# ---------------------------------------------------------------------------


def test_trigger_fraction_unset_uses_default() -> None:
    assert validators.validate_sacp_conclude_phase_trigger_fraction() is None


@pytest.mark.parametrize("value", ["0.5", "0.8", "0.85", "0.99", "0.001"])
def test_trigger_fraction_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_CONCLUDE_PHASE_TRIGGER_FRACTION", value)
    assert validators.validate_sacp_conclude_phase_trigger_fraction() is None


@pytest.mark.parametrize("value", ["0.0", "1.0", "-0.1", "1.5", "2.0"])
def test_trigger_fraction_out_of_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_CONCLUDE_PHASE_TRIGGER_FRACTION", value)
    failure = validators.validate_sacp_conclude_phase_trigger_fraction()
    assert failure is not None
    assert failure.var_name == "SACP_CONCLUDE_PHASE_TRIGGER_FRACTION"


def test_trigger_fraction_non_float(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_CONCLUDE_PHASE_TRIGGER_FRACTION", "fast")
    failure = validators.validate_sacp_conclude_phase_trigger_fraction()
    assert failure is not None
    assert "float" in failure.reason


# ---------------------------------------------------------------------------
# SACP_CONCLUDE_PHASE_PROMPT_TIER
# ---------------------------------------------------------------------------


def test_prompt_tier_unset_uses_default() -> None:
    assert validators.validate_sacp_conclude_phase_prompt_tier() is None


@pytest.mark.parametrize("value", ["1", "2", "3", "4"])
def test_prompt_tier_in_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_CONCLUDE_PHASE_PROMPT_TIER", value)
    assert validators.validate_sacp_conclude_phase_prompt_tier() is None


@pytest.mark.parametrize("value", ["0", "5", "-1", "10"])
def test_prompt_tier_out_of_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_CONCLUDE_PHASE_PROMPT_TIER", value)
    failure = validators.validate_sacp_conclude_phase_prompt_tier()
    assert failure is not None
    assert failure.var_name == "SACP_CONCLUDE_PHASE_PROMPT_TIER"


# ---------------------------------------------------------------------------
# Aggregate: all five validators registered in VALIDATORS tuple
# ---------------------------------------------------------------------------


def test_all_five_validators_registered() -> None:
    """T008 sanity: each of the five new validators is in the VALIDATORS tuple."""
    names = {v.__name__ for v in validators.VALIDATORS}
    assert "validate_sacp_length_cap_default_kind" in names
    assert "validate_sacp_length_cap_default_seconds" in names
    assert "validate_sacp_length_cap_default_turns" in names
    assert "validate_sacp_conclude_phase_trigger_fraction" in names
    assert "validate_sacp_conclude_phase_prompt_tier" in names
