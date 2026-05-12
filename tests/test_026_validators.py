# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 V16 validator unit tests (T009 of tasks.md).

Covers each of the four NEW SACP_* validators per spec 026 FR-025 and
contracts/env-vars.md:

- SACP_CACHE_OPENAI_KEY_STRATEGY
- SACP_COMPRESSION_PHASE2_ENABLED
- SACP_COMPRESSION_THRESHOLD_TOKENS
- SACP_COMPRESSION_DEFAULT_COMPRESSOR

Plus the cross-validator interaction validator
validate_compression_cross_var_interactions per
contracts/env-vars.md "Cross-validator interaction" section.

Each validator: valid value passes; out-of-range/out-of-set value
returns a ValidationFailure naming the offending var; empty handled
per the var's allowed-empty rule (all four accept unset/empty).
"""

from __future__ import annotations

import pytest

from src.config import validators


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the spec-026 vars unset."""
    for var in (
        "SACP_CACHE_OPENAI_KEY_STRATEGY",
        "SACP_COMPRESSION_PHASE2_ENABLED",
        "SACP_COMPRESSION_THRESHOLD_TOKENS",
        "SACP_COMPRESSION_DEFAULT_COMPRESSOR",
        "SACP_TOPOLOGY",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# SACP_CACHE_OPENAI_KEY_STRATEGY
# ---------------------------------------------------------------------------


def test_cache_openai_key_strategy_unset_passes() -> None:
    assert validators.validate_cache_openai_key_strategy() is None


def test_cache_openai_key_strategy_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_CACHE_OPENAI_KEY_STRATEGY", "")
    assert validators.validate_cache_openai_key_strategy() is None


@pytest.mark.parametrize("value", ["session_id", "participant_id"])
def test_cache_openai_key_strategy_in_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_CACHE_OPENAI_KEY_STRATEGY", value)
    assert validators.validate_cache_openai_key_strategy() is None


@pytest.mark.parametrize("value", ["sessionid", "PARTICIPANT_ID", "request_id", "x"])
def test_cache_openai_key_strategy_out_of_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_CACHE_OPENAI_KEY_STRATEGY", value)
    failure = validators.validate_cache_openai_key_strategy()
    assert failure is not None
    assert failure.var_name == "SACP_CACHE_OPENAI_KEY_STRATEGY"


# ---------------------------------------------------------------------------
# SACP_COMPRESSION_PHASE2_ENABLED
# ---------------------------------------------------------------------------


def test_phase2_enabled_unset_passes() -> None:
    assert validators.validate_compression_phase2_enabled() is None


def test_phase2_enabled_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "")
    assert validators.validate_compression_phase2_enabled() is None


@pytest.mark.parametrize("value", ["true", "false"])
def test_phase2_enabled_in_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", value)
    assert validators.validate_compression_phase2_enabled() is None


@pytest.mark.parametrize("value", ["TRUE", "FALSE", "1", "0", "yes", "no"])
def test_phase2_enabled_out_of_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", value)
    failure = validators.validate_compression_phase2_enabled()
    assert failure is not None
    assert failure.var_name == "SACP_COMPRESSION_PHASE2_ENABLED"


# ---------------------------------------------------------------------------
# SACP_COMPRESSION_THRESHOLD_TOKENS
# ---------------------------------------------------------------------------


def test_threshold_tokens_unset_passes() -> None:
    assert validators.validate_compression_threshold_tokens() is None


def test_threshold_tokens_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_THRESHOLD_TOKENS", "")
    assert validators.validate_compression_threshold_tokens() is None


@pytest.mark.parametrize("value", ["500", "1000", "4000", "16000", "100000"])
def test_threshold_tokens_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_THRESHOLD_TOKENS", value)
    assert validators.validate_compression_threshold_tokens() is None


@pytest.mark.parametrize("value", ["0", "1", "499", "100001", "1000000", "-100"])
def test_threshold_tokens_out_of_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_THRESHOLD_TOKENS", value)
    failure = validators.validate_compression_threshold_tokens()
    assert failure is not None
    assert failure.var_name == "SACP_COMPRESSION_THRESHOLD_TOKENS"


@pytest.mark.parametrize("value", ["abc", "4k", "4000.5", "5e3"])
def test_threshold_tokens_non_integer(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_THRESHOLD_TOKENS", value)
    failure = validators.validate_compression_threshold_tokens()
    assert failure is not None
    assert failure.var_name == "SACP_COMPRESSION_THRESHOLD_TOKENS"
    assert "integer" in failure.reason


# ---------------------------------------------------------------------------
# SACP_COMPRESSION_DEFAULT_COMPRESSOR
# ---------------------------------------------------------------------------


def test_default_compressor_unset_passes() -> None:
    assert validators.validate_compression_default_compressor() is None


def test_default_compressor_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", "")
    assert validators.validate_compression_default_compressor() is None


@pytest.mark.parametrize(
    "value",
    ["noop", "llmlingua2_mbert", "selective_context", "provence", "layer6"],
)
def test_default_compressor_in_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", value)
    assert validators.validate_compression_default_compressor() is None


@pytest.mark.parametrize("value", ["NoOp", "llmlingua", "selectivecontext", "xyz", "compress"])
def test_default_compressor_out_of_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", value)
    failure = validators.validate_compression_default_compressor()
    assert failure is not None
    assert failure.var_name == "SACP_COMPRESSION_DEFAULT_COMPRESSOR"


# ---------------------------------------------------------------------------
# Cross-validator interactions
# ---------------------------------------------------------------------------


def test_cross_var_defaults_pass() -> None:
    """All defaults (unset env) pass cross-validator checks."""
    assert validators.validate_compression_cross_var_interactions() is None


def test_cross_var_phase2_false_default_llmlingua_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 2 off + Phase 2 compressor default is impossible combo."""
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "false")
    monkeypatch.setenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", "llmlingua2_mbert")
    failure = validators.validate_compression_cross_var_interactions()
    assert failure is not None
    assert failure.var_name == "SACP_COMPRESSION_DEFAULT_COMPRESSOR"
    assert "SACP_COMPRESSION_PHASE2_ENABLED" in failure.reason


def test_cross_var_phase2_false_default_selective_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "false")
    monkeypatch.setenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", "selective_context")
    failure = validators.validate_compression_cross_var_interactions()
    assert failure is not None
    assert failure.var_name == "SACP_COMPRESSION_DEFAULT_COMPRESSOR"


def test_cross_var_phase2_true_default_llmlingua_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "true")
    monkeypatch.setenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", "llmlingua2_mbert")
    assert validators.validate_compression_cross_var_interactions() is None


def test_cross_var_topology_7_with_non_noop_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_TOPOLOGY", "7")
    monkeypatch.setenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", "llmlingua2_mbert")
    monkeypatch.setenv("SACP_COMPRESSION_PHASE2_ENABLED", "true")
    failure = validators.validate_compression_cross_var_interactions()
    assert failure is not None
    assert failure.var_name == "SACP_COMPRESSION_DEFAULT_COMPRESSOR"
    assert "topology" in failure.reason.lower() or "SACP_TOPOLOGY" in failure.reason


def test_cross_var_topology_7_with_noop_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_TOPOLOGY", "7")
    monkeypatch.setenv("SACP_COMPRESSION_DEFAULT_COMPRESSOR", "noop")
    assert validators.validate_compression_cross_var_interactions() is None


# ---------------------------------------------------------------------------
# VALIDATORS tuple registration
# ---------------------------------------------------------------------------


def test_all_new_validators_registered() -> None:
    """All five new validator callables MUST be registered in VALIDATORS."""
    expected = {
        validators.validate_cache_openai_key_strategy,
        validators.validate_compression_phase2_enabled,
        validators.validate_compression_threshold_tokens,
        validators.validate_compression_default_compressor,
        validators.validate_compression_cross_var_interactions,
    }
    assert expected.issubset(
        set(validators.VALIDATORS)
    ), "Spec 026 validators missing from VALIDATORS tuple"
