# SPDX-License-Identifier: AGPL-3.0-or-later

"""Validator unit tests for spec 020's two new SACP_* env vars."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config.validators import (
    validate_provider_adapter,
    validate_provider_adapter_mock_fixtures_path,
)


def _set_env(monkeypatch: pytest.MonkeyPatch, name: str, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)


def test_provider_adapter_default_unset_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", None)
    assert validate_provider_adapter() is None


def test_provider_adapter_litellm_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", "litellm")
    assert validate_provider_adapter() is None


def test_provider_adapter_mock_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", "mock")
    assert validate_provider_adapter() is None


def test_provider_adapter_uppercase_folded(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", "LITELLM")
    assert validate_provider_adapter() is None


def test_provider_adapter_invalid_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", "rabbit")
    failure = validate_provider_adapter()
    assert failure is not None
    assert failure.var_name == "SACP_PROVIDER_ADAPTER"
    assert "rabbit" in failure.reason
    assert "litellm" in failure.reason
    assert "mock" in failure.reason


def test_fixtures_path_ignored_when_adapter_litellm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", "litellm")
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH", None)
    assert validate_provider_adapter_mock_fixtures_path() is None


def test_fixtures_path_required_when_mock_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", "mock")
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH", None)
    failure = validate_provider_adapter_mock_fixtures_path()
    assert failure is not None
    assert failure.var_name == "SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH"
    assert "requires" in failure.reason


def test_fixtures_path_not_a_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", "mock")
    _set_env(
        monkeypatch,
        "SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH",
        str(tmp_path / "missing.json"),
    )
    failure = validate_provider_adapter_mock_fixtures_path()
    assert failure is not None
    assert "not a readable file" in failure.reason


def test_fixtures_path_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", "mock")
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH", str(bad))
    failure = validate_provider_adapter_mock_fixtures_path()
    assert failure is not None
    assert "invalid JSON" in failure.reason


def test_fixtures_path_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    good = tmp_path / "good.json"
    good.write_text(
        json.dumps({"responses": [], "errors": [], "capabilities": {}}),
        encoding="utf-8",
    )
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER", "mock")
    _set_env(monkeypatch, "SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH", str(good))
    assert validate_provider_adapter_mock_fixtures_path() is None
