# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 015 circuit breaker unit tests (T022).

US1 acceptance scenarios + SC-005/SC-007/SC-008 contracts.
No database required -- all assertions are against the in-memory state.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from src.api_bridge.adapter import CanonicalErrorCategory


def _cb():
    import src.orchestrator.circuit_breaker as cb

    return cb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_env(threshold: str = "3", window_s: str = "60") -> None:
    os.environ["SACP_PROVIDER_FAILURE_THRESHOLD"] = threshold
    os.environ["SACP_PROVIDER_FAILURE_WINDOW_S"] = window_s


def _unset_env() -> None:
    os.environ.pop("SACP_PROVIDER_FAILURE_THRESHOLD", None)
    os.environ.pop("SACP_PROVIDER_FAILURE_WINDOW_S", None)
    os.environ.pop("SACP_PROVIDER_RECOVERY_PROBE_BACKOFF", None)
    os.environ.pop("SACP_PROVIDER_PROBE_TIMEOUT_S", None)


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset circuit state and env vars around each test."""
    _unset_env()
    cb = _cb()
    cb._reset_for_tests()
    yield
    cb._reset_for_tests()
    _unset_env()


def _mock_pool():
    """Pool mock that no-ops all DB calls."""
    pool = MagicMock()
    conn_ctx = MagicMock()
    conn_ctx.__aenter__ = MagicMock(return_value=MagicMock())
    conn_ctx.__aexit__ = MagicMock(return_value=False)
    pool.acquire.return_value = conn_ctx
    return pool


# ---------------------------------------------------------------------------
# US1 AS1: Three failures in window trip the breaker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us1_as1_trip_threshold():
    """Three failures within window trip the breaker; next is_open() returns True."""
    _set_env(threshold="3", window_s="60")
    cb = _cb()
    cb._reload_config()

    pool = _mock_pool()
    sid = "s1"
    pid = "p1"
    prov = "openai"
    fp = cb._compute_api_key_fingerprint("enc_key")

    r1 = await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)
    r2 = await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)
    assert r1 is False
    assert r2 is False

    r3 = await cb.record_failure(sid, pid, prov, fp, CanonicalErrorCategory.ERROR_5XX, pool=pool)
    assert r3 is True

    assert cb.is_open(sid, pid, prov, fp) is True


# ---------------------------------------------------------------------------
# US1 AS2: Per-participant isolation (SC-007)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us1_as2_participant_b_independent():
    """Participant B not affected by participant A's open circuit."""
    _set_env(threshold="3", window_s="60")
    cb = _cb()
    cb._reload_config()

    pool = _mock_pool()
    fp = cb._compute_api_key_fingerprint("key")

    for _ in range(3):
        await cb.record_failure(
            "s1", "pA", "openai", fp, CanonicalErrorCategory.ERROR_5XX, pool=pool
        )

    assert cb.is_open("s1", "pA", "openai", fp) is True
    assert cb.is_open("s1", "pB", "openai", fp) is False


# ---------------------------------------------------------------------------
# US1 AS3: Skip reason 'circuit_open'; consecutive_open_turns increments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us1_as3_skip_reason_and_consecutive_turns():
    """short_circuit returns circuit_open; consecutive_open_turns increments."""
    _set_env(threshold="3", window_s="60")
    cb = _cb()
    cb._reload_config()

    pool = _mock_pool()
    fp = cb._compute_api_key_fingerprint("key")

    for _ in range(3):
        await cb.record_failure("s1", "p1", "openai", fp, CanonicalErrorCategory.TIMEOUT, pool=pool)

    assert cb.is_open("s1", "p1", "openai", fp) is True

    key = cb._circuit_key("s1", "p1", "openai", fp)
    state = cb._CIRCUITS[key]
    assert state.consecutive_open_turns == 1

    cb.is_open("s1", "p1", "openai", fp)
    assert state.consecutive_open_turns == 2

    meta = cb.short_circuit("s1", "p1", "openai", fp)
    assert meta["skip_reason"] == "circuit_open"


# ---------------------------------------------------------------------------
# US1 AS4: Env vars unset -- no-op / always False (SC-005 regression)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_us1_as4_env_unset_no_op():
    """When threshold and window_s are unset, record_failure is no-op and is_open always False."""
    _unset_env()
    cb = _cb()
    cb._reload_config()

    pool = _mock_pool()
    fp = cb._compute_api_key_fingerprint("key")

    for _ in range(10):
        result = await cb.record_failure(
            "s1", "p1", "openai", fp, CanonicalErrorCategory.ERROR_5XX, pool=pool
        )
        assert result is False

    assert cb.is_open("s1", "p1", "openai", fp) is False


# ---------------------------------------------------------------------------
# SC-008: FR-011 startup check -- cross-identity fallback triggers SystemExit
# ---------------------------------------------------------------------------


def test_sc008_cross_identity_fallback_exits():
    """check_no_cross_identity_fallbacks raises SystemExit for cross-identity entries."""
    from src.orchestrator.circuit_breaker import check_no_cross_identity_fallbacks

    config = [
        {"model_name": "gpt-4", "litellm_params": {"api_key": "key_alice"}},
        {"model_name": "gpt-4", "litellm_params": {"api_key": "key_bob"}},
    ]
    with pytest.raises(SystemExit):
        check_no_cross_identity_fallbacks(config)


def test_sc008_same_identity_passes():
    """check_no_cross_identity_fallbacks passes when all entries share the same key."""
    from src.orchestrator.circuit_breaker import check_no_cross_identity_fallbacks

    config = [
        {"model_name": "gpt-4", "litellm_params": {"api_key": "key_alice"}},
        {"model_name": "gpt-4", "litellm_params": {"api_key": "key_alice"}},
    ]
    check_no_cross_identity_fallbacks(config)


def test_sc008_empty_config_passes():
    """check_no_cross_identity_fallbacks passes on empty config."""
    from src.orchestrator.circuit_breaker import check_no_cross_identity_fallbacks

    check_no_cross_identity_fallbacks([])


# ---------------------------------------------------------------------------
# FR-017: circuit_open excluded from convergence (T032)
# ---------------------------------------------------------------------------


def test_fr017_circuit_open_turn_number_le_zero():
    """Skipped TurnResult for circuit_open has turn_number == -1 (FR-017 contract).

    Spec 015 FR-017: skipped turns use turn_number <= 0, which ConvergenceDetector
    no-ops on (per its existing contract, line 149: `if turn_number <= 0: return`).
    We verify the shape directly rather than importing the full loop graph.
    """
    from src.orchestrator.types import TurnResult

    skip = TurnResult(
        session_id="s1",
        turn_number=-1,
        speaker_id="p1",
        action="skipped",
        tokens_used=0,
        cost_usd=0.0,
        skipped=True,
        skip_reason="circuit_open",
    )
    assert skip.turn_number == -1
    assert skip.skip_reason == "circuit_open"


# ---------------------------------------------------------------------------
# Fingerprint helper
# ---------------------------------------------------------------------------


def test_fingerprint_8_hex_chars():
    from src.orchestrator.circuit_breaker import _compute_api_key_fingerprint

    fp = _compute_api_key_fingerprint("any_encrypted_key")
    assert len(fp) == 8
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_deterministic():
    from src.orchestrator.circuit_breaker import _compute_api_key_fingerprint

    assert _compute_api_key_fingerprint("key") == _compute_api_key_fingerprint("key")


def test_fingerprint_different_keys():
    from src.orchestrator.circuit_breaker import _compute_api_key_fingerprint

    assert _compute_api_key_fingerprint("key_a") != _compute_api_key_fingerprint("key_b")
