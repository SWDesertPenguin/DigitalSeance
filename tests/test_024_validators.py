# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 024 validator coverage (FR-022 V16 gate).

Three new SACP_SCRATCH_* env vars; each has a validator in
src/config/validators.py and is registered in the VALIDATORS tuple.
"""

from __future__ import annotations

import pytest

from src.config.validators import (
    VALIDATORS,
    validate_scratch_enabled,
    validate_scratch_note_max_kb,
    validate_scratch_retention_days_after_archive,
)

# ---- SACP_SCRATCH_ENABLED ----


def test_scratch_enabled_default_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SACP_SCRATCH_ENABLED", raising=False)
    assert validate_scratch_enabled() is None


def test_scratch_enabled_accepts_0_and_1(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("0", "1"):
        monkeypatch.setenv("SACP_SCRATCH_ENABLED", value)
        assert validate_scratch_enabled() is None


def test_scratch_enabled_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("true", "yes", "ON", "2"):
        monkeypatch.setenv("SACP_SCRATCH_ENABLED", value)
        failure = validate_scratch_enabled()
        assert failure is not None
        assert failure.var_name == "SACP_SCRATCH_ENABLED"


# ---- SACP_SCRATCH_NOTE_MAX_KB ----


def test_note_max_kb_default_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SACP_SCRATCH_NOTE_MAX_KB", raising=False)
    assert validate_scratch_note_max_kb() is None


def test_note_max_kb_accepts_in_range(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("1", "64", "1024"):
        monkeypatch.setenv("SACP_SCRATCH_NOTE_MAX_KB", value)
        assert validate_scratch_note_max_kb() is None


def test_note_max_kb_rejects_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("0", "1025", "-5"):
        monkeypatch.setenv("SACP_SCRATCH_NOTE_MAX_KB", value)
        failure = validate_scratch_note_max_kb()
        assert failure is not None


def test_note_max_kb_rejects_non_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_SCRATCH_NOTE_MAX_KB", "abc")
    failure = validate_scratch_note_max_kb()
    assert failure is not None
    assert "integer" in failure.reason


# ---- SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE ----


def test_retention_days_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE", raising=False)
    assert validate_scratch_retention_days_after_archive() is None


def test_retention_days_accepts_in_range(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("1", "30", "36500"):
        monkeypatch.setenv("SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE", value)
        assert validate_scratch_retention_days_after_archive() is None


def test_retention_days_rejects_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("0", "36501", "-1"):
        monkeypatch.setenv("SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE", value)
        failure = validate_scratch_retention_days_after_archive()
        assert failure is not None


def test_retention_days_rejects_non_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE", "thirty")
    failure = validate_scratch_retention_days_after_archive()
    assert failure is not None
    assert "integer" in failure.reason


# ---- VALIDATORS tuple registration ----


def test_validators_tuple_contains_all_three() -> None:
    names = {v.__name__ for v in VALIDATORS}
    for expected in (
        "validate_scratch_enabled",
        "validate_scratch_note_max_kb",
        "validate_scratch_retention_days_after_archive",
    ):
        assert expected in names
