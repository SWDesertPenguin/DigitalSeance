# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 025 effective_active_seconds helper (T051 partial of tasks.md).

Pure-function tests for the elapsed-time read helper used by both the
loop's cap-check and the cap-set endpoint. Per the helper's
docstring, when the durable accumulator is null it falls back to
`(now() - created_at)`. Pause-aware accumulator is queued under
T052 and lands in a follow-up commit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.orchestrator.length_cap import effective_active_seconds


class _FakeSession:
    def __init__(self, **fields: object) -> None:
        for name, value in fields.items():
            setattr(self, name, value)


def test_uses_durable_accumulator_when_set() -> None:
    session = _FakeSession(
        active_seconds_accumulator=600,
        created_at=datetime.now(UTC) - timedelta(hours=10),
    )
    assert effective_active_seconds(session) == 600


def test_falls_back_to_created_at_when_accumulator_null() -> None:
    """No accumulator set → derive from created_at."""
    created = datetime.now(UTC) - timedelta(seconds=120)
    session = _FakeSession(active_seconds_accumulator=None, created_at=created)
    out = effective_active_seconds(session)
    # 120 seconds elapsed; allow ~5s tolerance for test execution.
    assert 118 <= out <= 130


def test_zero_when_neither_field_present() -> None:
    """Edge: a stub session row missing both fields → 0."""
    session = _FakeSession(active_seconds_accumulator=None, created_at=None)
    assert effective_active_seconds(session) == 0


def test_handles_naive_datetime() -> None:
    """Some test fixtures pass naive datetimes; helper must not crash."""
    created = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=60)
    session = _FakeSession(active_seconds_accumulator=None, created_at=created)
    out = effective_active_seconds(session)
    assert out >= 58


def test_zero_accumulator_uses_durable_value() -> None:
    """Accumulator=0 is a real value (session just started); use it, don't fall back."""
    session = _FakeSession(
        active_seconds_accumulator=0,
        created_at=datetime.now(UTC) - timedelta(hours=10),
    )
    assert effective_active_seconds(session) == 0
