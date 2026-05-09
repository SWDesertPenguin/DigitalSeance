# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the turn-loop skip-spam backoff helper."""

from __future__ import annotations

from dataclasses import dataclass

from src.mcp_server.tools.session import (
    _SKIP_BACKOFF_BASE_S,
    _SKIP_BACKOFF_MAX_S,
    _log_and_count,
    _tick_delay,
)


@dataclass
class _FakeResult:
    skipped: bool = False
    skip_reason: str | None = None
    delay_seconds: float | None = None
    speaker_id: str = "spk"
    turn_number: int = 0


def test_tick_delay_zero_for_completed_turn() -> None:
    result = _FakeResult(skipped=False, delay_seconds=None)
    assert _tick_delay(result, skips=0) == 0.0


def test_tick_delay_uses_turn_delay_when_set() -> None:
    result = _FakeResult(skipped=False, delay_seconds=12.5)
    assert _tick_delay(result, skips=0) == 12.5


def test_tick_delay_backoff_doubles_on_skip() -> None:
    """First skip → base; second → 2×; third → 4×; caps at MAX."""
    result = _FakeResult(skipped=True)
    assert _tick_delay(result, skips=1) == _SKIP_BACKOFF_BASE_S
    assert _tick_delay(result, skips=2) == _SKIP_BACKOFF_BASE_S * 2
    assert _tick_delay(result, skips=3) == _SKIP_BACKOFF_BASE_S * 4
    assert _tick_delay(result, skips=30) == _SKIP_BACKOFF_MAX_S


def test_log_and_count_resets_on_real_turn() -> None:
    """A non-skipped result resets the consecutive-skip counter to 0."""
    assert _log_and_count(_FakeResult(skipped=False), skips=5) == 0


def test_log_and_count_increments_on_skip() -> None:
    """Every skip increments the counter by one."""
    assert _log_and_count(_FakeResult(skipped=True), skips=0) == 1
    assert _log_and_count(_FakeResult(skipped=True), skips=7) == 8
