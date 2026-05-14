# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 015 probe recovery tests (T028).

US2 acceptance scenarios. No database required.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api_bridge.adapter import CanonicalErrorCategory, ValidationResult


def _cb():
    import src.orchestrator.circuit_breaker as cb

    return cb


def _set_env(**kwargs) -> None:
    for k, v in kwargs.items():
        os.environ[k] = v


def _unset_env() -> None:
    os.environ.pop("SACP_PROVIDER_FAILURE_THRESHOLD", None)
    os.environ.pop("SACP_PROVIDER_FAILURE_WINDOW_S", None)
    os.environ.pop("SACP_PROVIDER_RECOVERY_PROBE_BACKOFF", None)
    os.environ.pop("SACP_PROVIDER_PROBE_TIMEOUT_S", None)


def _mock_pool():
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=None)
    conn_ctx = MagicMock()
    conn_ctx.__aenter__ = AsyncMock(return_value=conn)
    conn_ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = conn_ctx
    return pool


@pytest.fixture(autouse=True)
def _clean():
    _unset_env()
    cb = _cb()
    cb._reset_for_tests()
    yield
    cb._reset_for_tests()
    _unset_env()


def _trip_breaker_sync(cb_module, session_id, participant_id, provider, fp, pool, threshold=3):
    """Helper to trip a breaker by recording `threshold` failures."""
    import asyncio as _asyncio

    async def _trip():
        for _ in range(threshold):
            await cb_module.record_failure(
                session_id,
                participant_id,
                provider,
                fp,
                CanonicalErrorCategory.ERROR_5XX,
                pool=pool,
            )

    _asyncio.get_event_loop().run_until_complete(_trip())


# ---------------------------------------------------------------------------
# US2 AS2: Probe success closes breaker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us2_as2_probe_success_closes_breaker():
    """Mock adapter returning ValidationResult.ok=True closes the breaker."""
    _set_env(
        SACP_PROVIDER_FAILURE_THRESHOLD="3",
        SACP_PROVIDER_FAILURE_WINDOW_S="60",
        SACP_PROVIDER_RECOVERY_PROBE_BACKOFF="1",
        SACP_PROVIDER_PROBE_TIMEOUT_S="5",
    )
    cb = _cb()
    cb._reload_config()
    pool = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    assert cb.is_open(sid, pid, prov, fp) is True

    mock_adapter = MagicMock()
    mock_adapter.validate_credentials = AsyncMock(return_value=ValidationResult(ok=True))

    key = cb._circuit_key(sid, pid, prov, fp)
    state = cb._CIRCUITS[key]

    with patch("src.api_bridge.adapter.get_adapter", return_value=mock_adapter):
        await cb._run_probe(state)

    assert state.state == "closed"
    assert cb.is_open(sid, pid, prov, fp) is False


# ---------------------------------------------------------------------------
# US2 AS3: Probe failure keeps open, schedule advances
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us2_as3_probe_failure_stays_open_schedule_advances():
    """Probe failure keeps breaker open and increments schedule position."""
    _set_env(
        SACP_PROVIDER_FAILURE_THRESHOLD="3",
        SACP_PROVIDER_FAILURE_WINDOW_S="60",
        SACP_PROVIDER_RECOVERY_PROBE_BACKOFF="1,5,30",
        SACP_PROVIDER_PROBE_TIMEOUT_S="5",
    )
    cb = _cb()
    cb._reload_config()
    pool = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    key = cb._circuit_key(sid, pid, prov, fp)
    state = cb._CIRCUITS[key]
    assert state.probe_schedule_position == 0

    mock_adapter = MagicMock()
    mock_adapter.validate_credentials = AsyncMock(return_value=ValidationResult(ok=False))

    with patch("src.api_bridge.adapter.get_adapter", return_value=mock_adapter):
        await cb._run_probe(state)

    assert state.state == "open"
    assert state.probe_schedule_position == 1


# ---------------------------------------------------------------------------
# US2 AS3 (exhausted): cycle-on-last semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us2_as3_exhausted_cycle_on_last():
    """At last schedule position, probe_schedule_position stays pinned (cycle-on-last)."""
    _set_env(
        SACP_PROVIDER_FAILURE_THRESHOLD="3",
        SACP_PROVIDER_FAILURE_WINDOW_S="60",
        SACP_PROVIDER_RECOVERY_PROBE_BACKOFF="1,5",
        SACP_PROVIDER_PROBE_TIMEOUT_S="5",
    )
    cb = _cb()
    cb._reload_config()
    pool = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    key = cb._circuit_key(sid, pid, prov, fp)
    state = cb._CIRCUITS[key]
    state.probe_schedule_position = 1

    mock_adapter = MagicMock()
    mock_adapter.validate_credentials = AsyncMock(return_value=ValidationResult(ok=False))

    with patch("src.api_bridge.adapter.get_adapter", return_value=mock_adapter):
        await cb._run_probe(state)

    assert state.probe_schedule_position == 1


# ---------------------------------------------------------------------------
# US2 AS4: close_on_key_update fast-close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us2_as4_close_on_key_update():
    """close_on_key_update closes immediately with trigger_reason='api_key_update'."""
    _set_env(
        SACP_PROVIDER_FAILURE_THRESHOLD="3",
        SACP_PROVIDER_FAILURE_WINDOW_S="60",
    )
    cb = _cb()
    cb._reload_config()
    pool = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    assert cb.is_open(sid, pid, prov, fp) is True

    await cb.close_on_key_update(sid, pid, pool)

    assert cb.is_open(sid, pid, prov, fp) is False
    assert (sid, pid, prov, fp) not in cb._CIRCUITS


# ---------------------------------------------------------------------------
# US2 AS4: in-flight probe cancelled on close_on_key_update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us2_as4_in_flight_probe_cancelled():
    """close_on_key_update cancels an in-flight probe task."""
    _set_env(
        SACP_PROVIDER_FAILURE_THRESHOLD="3",
        SACP_PROVIDER_FAILURE_WINDOW_S="60",
    )
    cb = _cb()
    cb._reload_config()
    pool = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    key = cb._circuit_key(sid, pid, prov, fp)
    state = cb._CIRCUITS[key]

    # Simulate an in-flight probe task
    async def _noop():
        await asyncio.sleep(100)

    task = asyncio.create_task(_noop())
    state._probe_task = task

    await cb.close_on_key_update(sid, pid, pool)
    # Allow the cancellation to propagate
    import contextlib

    with contextlib.suppress(asyncio.CancelledError, Exception):
        await asyncio.shield(task)
    assert task.cancelled() or task.cancelling() > 0


# ---------------------------------------------------------------------------
# US2 AS1: exactly one probe per backoff tick (guard against double-launch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us2_as1_one_probe_per_tick():
    """Guard: if _probe_task is not done, _maybe_launch_probe skips duplicate launch."""
    _set_env(
        SACP_PROVIDER_FAILURE_THRESHOLD="3",
        SACP_PROVIDER_FAILURE_WINDOW_S="60",
        SACP_PROVIDER_RECOVERY_PROBE_BACKOFF="1",
    )
    cb = _cb()
    cb._reload_config()
    pool = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    key = cb._circuit_key(sid, pid, prov, fp)
    state = cb._CIRCUITS[key]
    state.state = "open"

    async def _long_probe():
        await asyncio.sleep(100)

    task = asyncio.create_task(_long_probe())
    state._probe_task = task

    cb._maybe_launch_probe(state)

    assert state._probe_task is task
    task.cancel()
    import contextlib

    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task
