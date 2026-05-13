# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 018 — V16 validator unit tests. Phase-1 V16 gate."""

from __future__ import annotations

import pytest

from src.config.validators import (
    validate_sacp_tool_defer_enabled,
    validate_sacp_tool_defer_index_max_tokens,
    validate_sacp_tool_defer_load_timeout_s,
    validate_sacp_tool_loaded_token_budget,
)


def test_defer_enabled_unset_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("SACP_TOOL_DEFER_ENABLED", raising=False)
    assert validate_sacp_tool_defer_enabled() is None


@pytest.mark.parametrize("value", ["true", "True", "TRUE", "false", "False", "FALSE"])
def test_defer_enabled_valid_passes(monkeypatch, value: str) -> None:
    monkeypatch.setenv("SACP_TOOL_DEFER_ENABLED", value)
    assert validate_sacp_tool_defer_enabled() is None


@pytest.mark.parametrize("value", ["maybe", "1", "0", "yes", "no", "garbage", "TRUEFALSE"])
def test_defer_enabled_invalid_fails(monkeypatch, value: str) -> None:
    monkeypatch.setenv("SACP_TOOL_DEFER_ENABLED", value)
    fail = validate_sacp_tool_defer_enabled()
    assert fail is not None
    assert fail.var_name == "SACP_TOOL_DEFER_ENABLED"
    assert "true" in fail.reason.lower() and "false" in fail.reason.lower()


def test_loaded_token_budget_unset_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("SACP_TOOL_LOADED_TOKEN_BUDGET", raising=False)
    assert validate_sacp_tool_loaded_token_budget() is None


@pytest.mark.parametrize("value", ["512", "1500", "4096", "8192"])
def test_loaded_token_budget_valid_passes(monkeypatch, value: str) -> None:
    monkeypatch.setenv("SACP_TOOL_LOADED_TOKEN_BUDGET", value)
    assert validate_sacp_tool_loaded_token_budget() is None


@pytest.mark.parametrize(
    "value,reason_part",
    [
        ("0", "[512, 8192]"),
        ("511", "[512, 8192]"),
        ("8193", "[512, 8192]"),
        ("-1", "[512, 8192]"),
        ("abc", "integer"),
        ("1.5", "integer"),
    ],
)
def test_loaded_token_budget_invalid_fails(monkeypatch, value: str, reason_part: str) -> None:
    monkeypatch.setenv("SACP_TOOL_LOADED_TOKEN_BUDGET", value)
    fail = validate_sacp_tool_loaded_token_budget()
    assert fail is not None
    assert fail.var_name == "SACP_TOOL_LOADED_TOKEN_BUDGET"
    assert reason_part in fail.reason


def test_defer_index_max_tokens_unset_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("SACP_TOOL_DEFER_INDEX_MAX_TOKENS", raising=False)
    assert validate_sacp_tool_defer_index_max_tokens() is None


@pytest.mark.parametrize("value", ["64", "256", "512", "1024"])
def test_defer_index_max_tokens_valid_passes(monkeypatch, value: str) -> None:
    monkeypatch.setenv("SACP_TOOL_DEFER_INDEX_MAX_TOKENS", value)
    assert validate_sacp_tool_defer_index_max_tokens() is None


@pytest.mark.parametrize("value", ["0", "63", "1025", "9999", "abc"])
def test_defer_index_max_tokens_invalid_fails(monkeypatch, value: str) -> None:
    monkeypatch.setenv("SACP_TOOL_DEFER_INDEX_MAX_TOKENS", value)
    fail = validate_sacp_tool_defer_index_max_tokens()
    assert fail is not None
    assert fail.var_name == "SACP_TOOL_DEFER_INDEX_MAX_TOKENS"


def test_defer_load_timeout_unset_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("SACP_TOOL_DEFER_LOAD_TIMEOUT_S", raising=False)
    assert validate_sacp_tool_defer_load_timeout_s() is None


@pytest.mark.parametrize("value", ["1", "10", "30"])
def test_defer_load_timeout_valid_passes(monkeypatch, value: str) -> None:
    monkeypatch.setenv("SACP_TOOL_DEFER_LOAD_TIMEOUT_S", value)
    assert validate_sacp_tool_defer_load_timeout_s() is None


@pytest.mark.parametrize("value", ["0", "31", "60", "-1", "abc"])
def test_defer_load_timeout_invalid_fails(monkeypatch, value: str) -> None:
    monkeypatch.setenv("SACP_TOOL_DEFER_LOAD_TIMEOUT_S", value)
    fail = validate_sacp_tool_defer_load_timeout_s()
    assert fail is not None
    assert fail.var_name == "SACP_TOOL_DEFER_LOAD_TIMEOUT_S"
