# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 015 audit and metrics tests (T030).

US3 acceptance scenarios.
DB-backed tests require PostgreSQL (skip-without-DB pattern per conftest).
"""

from __future__ import annotations

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


@pytest.fixture(autouse=True)
def _clean():
    _unset_env()
    cb = _cb()
    cb._reset_for_tests()
    yield
    cb._reset_for_tests()
    _unset_env()


def _make_conn_mock():
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=None)
    conn_ctx = MagicMock()
    conn_ctx.__aenter__ = AsyncMock(return_value=conn)
    conn_ctx.__aexit__ = AsyncMock(return_value=False)
    return conn, conn_ctx


def _mock_pool():
    conn, conn_ctx = _make_conn_mock()
    pool = MagicMock()
    pool.acquire.return_value = conn_ctx
    return pool, conn


# ---------------------------------------------------------------------------
# US3 AS1: trip emits provider_circuit_open_log row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us3_as1_trip_emits_open_log():
    """Trip emits an INSERT to provider_circuit_open_log with required fields."""
    _set_env(SACP_PROVIDER_FAILURE_THRESHOLD="3", SACP_PROVIDER_FAILURE_WINDOW_S="60")
    cb = _cb()
    cb._reload_config()
    pool, conn = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(2):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    conn.execute.reset_mock()
    just_opened = await cb.record_failure(
        sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool
    )
    assert just_opened is True

    import asyncio

    await asyncio.sleep(0)

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("provider_circuit_open_log" in c for c in calls)


# ---------------------------------------------------------------------------
# US3 AS2: metrics surface exposes open count and trigger reason (SC-004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us3_as2_metrics_snapshot():
    """get_metrics_snapshot returns open breaker with trigger_reason and open_since."""
    _set_env(SACP_PROVIDER_FAILURE_THRESHOLD="3", SACP_PROVIDER_FAILURE_WINDOW_S="60")
    cb = _cb()
    cb._reload_config()
    pool, _ = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.RATE_LIMIT, pool=pool)

    snapshot = cb.get_metrics_snapshot()
    assert len(snapshot) == 1
    snap = snapshot[0]
    assert snap.session_id == sid
    assert snap.participant_id == pid
    assert snap.trigger_reason == CanonicalErrorCategory.RATE_LIMIT.value
    assert snap.open_since is not None


@pytest.mark.asyncio
async def test_us3_as2_metrics_empty_when_no_open():
    """get_metrics_snapshot returns empty when no breakers are open."""
    _set_env(SACP_PROVIDER_FAILURE_THRESHOLD="3", SACP_PROVIDER_FAILURE_WINDOW_S="60")
    cb = _cb()
    cb._reload_config()

    snapshot = cb.get_metrics_snapshot()
    assert snapshot == []


# ---------------------------------------------------------------------------
# US3 AS3: close emits provider_circuit_close_log row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us3_as3_close_emits_close_log():
    """Probe success closes breaker and emits INSERT to provider_circuit_close_log."""
    _set_env(
        SACP_PROVIDER_FAILURE_THRESHOLD="3",
        SACP_PROVIDER_FAILURE_WINDOW_S="60",
        SACP_PROVIDER_RECOVERY_PROBE_BACKOFF="1",
        SACP_PROVIDER_PROBE_TIMEOUT_S="5",
    )
    cb = _cb()
    cb._reload_config()
    pool, conn = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    key = cb._circuit_key(sid, pid, prov, fp)
    state = cb._CIRCUITS[key]

    conn.execute.reset_mock()

    mock_adapter = MagicMock()
    mock_adapter.validate_credentials = AsyncMock(return_value=ValidationResult(ok=True))

    with patch("src.api_bridge.adapter.get_adapter", return_value=mock_adapter):
        await cb._run_probe(state)

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("provider_circuit_close_log" in c for c in calls)


# ---------------------------------------------------------------------------
# US3 AS3: close_on_key_update emits close log with trigger_reason='api_key_update'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us3_as3_close_on_key_update_emits_close_log():
    """close_on_key_update emits provider_circuit_close_log with api_key_update."""
    _set_env(SACP_PROVIDER_FAILURE_THRESHOLD="3", SACP_PROVIDER_FAILURE_WINDOW_S="60")
    cb = _cb()
    cb._reload_config()
    pool, conn = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.AUTH_ERROR, pool=pool)

    conn.execute.reset_mock()
    await cb.close_on_key_update(sid, pid, pool)

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("provider_circuit_close_log" in c for c in calls)
    assert any("api_key_update" in c for c in calls)


# ---------------------------------------------------------------------------
# US3 AS4: probe emits provider_circuit_probe_log row (success + failure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us3_as4_probe_log_on_success():
    """Successful probe emits INSERT to provider_circuit_probe_log."""
    _set_env(
        SACP_PROVIDER_FAILURE_THRESHOLD="3",
        SACP_PROVIDER_FAILURE_WINDOW_S="60",
        SACP_PROVIDER_RECOVERY_PROBE_BACKOFF="1",
        SACP_PROVIDER_PROBE_TIMEOUT_S="5",
    )
    cb = _cb()
    cb._reload_config()
    pool, conn = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    key = cb._circuit_key(sid, pid, prov, fp)
    state = cb._CIRCUITS[key]
    conn.execute.reset_mock()

    mock_adapter = MagicMock()
    mock_adapter.validate_credentials = AsyncMock(return_value=ValidationResult(ok=True))

    with patch("src.api_bridge.adapter.get_adapter", return_value=mock_adapter):
        await cb._run_probe(state)

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("provider_circuit_probe_log" in c for c in calls)


@pytest.mark.asyncio
async def test_us3_as4_probe_log_on_failure():
    """Failed probe emits INSERT to provider_circuit_probe_log."""
    _set_env(
        SACP_PROVIDER_FAILURE_THRESHOLD="3",
        SACP_PROVIDER_FAILURE_WINDOW_S="60",
        SACP_PROVIDER_RECOVERY_PROBE_BACKOFF="1",
        SACP_PROVIDER_PROBE_TIMEOUT_S="5",
    )
    cb = _cb()
    cb._reload_config()
    pool, conn = _mock_pool()

    fp = cb._compute_api_key_fingerprint("enc")
    sid, pid, prov = "s1", "p1", "openai"

    for _ in range(3):
        await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)

    key = cb._circuit_key(sid, pid, prov, fp)
    state = cb._CIRCUITS[key]
    conn.execute.reset_mock()

    mock_adapter = MagicMock()
    mock_adapter.validate_credentials = AsyncMock(return_value=ValidationResult(ok=False))

    with patch("src.api_bridge.adapter.get_adapter", return_value=mock_adapter):
        await cb._run_probe(state)

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("provider_circuit_probe_log" in c for c in calls)
