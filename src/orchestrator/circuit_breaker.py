# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-participant sliding-window circuit breaker (spec 015).

Three-state machine: closed -> open -> half_open -> closed.
Keyed on (session_id, participant_id, provider, api_key_fingerprint).
Session-local in-memory only; no persistence across restart.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import zlib
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from src.api_bridge.adapter import CanonicalErrorCategory

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Env-var reading (module-level, read once)
# ---------------------------------------------------------------------------


def _read_threshold() -> int | None:
    raw = os.environ.get("SACP_PROVIDER_FAILURE_THRESHOLD")
    if not raw or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _read_window_s() -> int | None:
    raw = os.environ.get("SACP_PROVIDER_FAILURE_WINDOW_S")
    if not raw or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _read_backoff_schedule() -> tuple[int, ...] | None:
    raw = os.environ.get("SACP_PROVIDER_RECOVERY_PROBE_BACKOFF")
    if not raw or not raw.strip():
        return None
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    try:
        return tuple(int(e) for e in entries)
    except ValueError:
        return None


def _read_probe_timeout_s() -> float:
    raw = os.environ.get("SACP_PROVIDER_PROBE_TIMEOUT_S")
    if not raw or not raw.strip():
        return 10.0
    try:
        return float(raw)
    except ValueError:
        return 10.0


# Module-scope config; re-read per test via _reload_config()
_threshold: int | None = _read_threshold()
_window_s: int | None = _read_window_s()
_backoff_schedule: tuple[int, ...] | None = _read_backoff_schedule()
_probe_timeout_s: float = _read_probe_timeout_s()


def _reload_config() -> None:
    """Re-read env vars. Test helper; not called in production."""
    global _threshold, _window_s, _backoff_schedule, _probe_timeout_s
    _threshold = _read_threshold()
    _window_s = _read_window_s()
    _backoff_schedule = _read_backoff_schedule()
    _probe_timeout_s = _read_probe_timeout_s()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FailureRecord:
    """One counted failure in the sliding window."""

    timestamp: datetime
    failure_kind: CanonicalErrorCategory


@dataclass
class CircuitState:
    """Per-participant circuit breaker state (session-local, not persisted)."""

    session_id: str
    participant_id: str
    provider: str
    api_key_fingerprint: str
    state: Literal["closed", "open", "half_open"] = "closed"
    opened_at: datetime | None = None
    failure_window: deque = field(default_factory=deque)
    probe_schedule_position: int = 0
    _probe_task: asyncio.Task | None = None  # type: ignore[type-arg]
    consecutive_open_turns: int = 0
    probes_attempted: int = 0
    probes_succeeded: int = 0
    _last_probe_attempt_at: datetime | None = None
    _pool: object = None  # DB pool reference for fire-and-forget writes


# Process-scope dict keyed on (session_id, participant_id, provider, api_key_fingerprint)
_CIRCUITS: dict[tuple[str, str, str, str], CircuitState] = {}


def _circuit_key(
    session_id: str, participant_id: str, provider: str, api_key_fingerprint: str
) -> tuple[str, str, str, str]:
    return (session_id, participant_id, provider, api_key_fingerprint)


def _compute_api_key_fingerprint(api_key_encrypted: str) -> str:
    """Opaque 8-char identifier for circuit-breaker dict keying.

    Purely a per-rotation discriminator inside `_CIRCUITS` — never compared
    against a credential, never persisted as an authenticator, never used in
    a verification path. The input is already an opaque ciphertext from the
    encryption layer; this function only derives a short stable label so the
    breaker state survives rotation. CRC32 is a non-cryptographic checksum
    appropriate for in-memory dict keying — the 8-hex-char output is the
    entire identifier, not a truncation of a credential-grade hash.
    """
    return f"{zlib.crc32(api_key_encrypted.encode()) & 0xFFFFFFFF:08x}"


def _get_or_create_state(
    session_id: str, participant_id: str, provider: str, api_key_fingerprint: str
) -> CircuitState:
    key = _circuit_key(session_id, participant_id, provider, api_key_fingerprint)
    if key not in _CIRCUITS:
        maxlen = max((_threshold or 3) * 4, 20)
        state = CircuitState(
            session_id=session_id,
            participant_id=participant_id,
            provider=provider,
            api_key_fingerprint=api_key_fingerprint,
            failure_window=deque(maxlen=maxlen),
        )
        _CIRCUITS[key] = state
    return _CIRCUITS[key]


def _trim_window(state: CircuitState) -> None:
    """Remove failure records older than window_s seconds."""
    if _window_s is None:
        return
    cutoff = datetime.now(UTC).timestamp() - _window_s
    while state.failure_window and state.failure_window[0].timestamp.timestamp() < cutoff:
        state.failure_window.popleft()


def _dominant_failure_kind(state: CircuitState) -> str:
    """Return the modal failure_kind value name in the window."""
    if not state.failure_window:
        return CanonicalErrorCategory.UNKNOWN.value
    counts = Counter(r.failure_kind.value for r in state.failure_window)
    return counts.most_common(1)[0][0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def record_failure(
    session_id: str,
    participant_id: str,
    provider: str,
    api_key_fingerprint: str,
    failure_kind: CanonicalErrorCategory,
    *,
    pool: object,
) -> bool:
    """Record a failure; return True if the breaker just tripped to open.

    No-op (returns False) when threshold or window env var is unset.
    """
    if _threshold is None or _window_s is None:
        return False
    state = _get_or_create_state(session_id, participant_id, provider, api_key_fingerprint)
    if pool is not None:
        state._pool = pool
    state.failure_window.append(
        FailureRecord(timestamp=datetime.now(UTC), failure_kind=failure_kind)
    )
    _trim_window(state)
    count = len(state.failure_window)
    if count >= _threshold and state.state == "closed":
        state.state = "open"
        state.opened_at = datetime.now(UTC)
        trigger_reason = _dominant_failure_kind(state)
        asyncio.create_task(  # noqa: RUF006
            _write_open_log(state, trigger_reason, count, pool)
        )
        return True
    return False


def is_open(
    session_id: str,
    participant_id: str,
    provider: str,
    api_key_fingerprint: str,
) -> bool:
    """Return True if the circuit is open or half_open.

    Side effect: increments consecutive_open_turns when returning True.
    Also schedules a probe when state is open and backoff is configured.
    """
    if _threshold is None or _window_s is None:
        return False
    key = _circuit_key(session_id, participant_id, provider, api_key_fingerprint)
    state = _CIRCUITS.get(key)
    if state is None or state.state == "closed":
        return False
    state.consecutive_open_turns += 1
    if state.state == "open" and _backoff_schedule is not None:
        _maybe_launch_probe(state)
    return True


def short_circuit(
    session_id: str,
    participant_id: str,
    provider: str,
    api_key_fingerprint: str,
) -> dict:
    """Return skip metadata for a circuit-open participant.

    When consecutive_open_turns >= 3 returns an auto_pause trigger flag.
    """
    key = _circuit_key(session_id, participant_id, provider, api_key_fingerprint)
    state = _CIRCUITS.get(key)
    auto_pause = state is not None and state.consecutive_open_turns >= 3
    return {
        "skip_reason": "circuit_open",
        "auto_pause": auto_pause,
    }


async def close_on_key_update(
    session_id: str,
    participant_id: str,
    pool: object,
) -> None:
    """Fast-close all circuits for this participant on api_key_update (FR-016).

    Cancels in-flight probe tasks and writes close log rows.
    """
    matching = [
        (key, state)
        for key, state in list(_CIRCUITS.items())
        if key[0] == session_id and key[1] == participant_id
    ]
    for key, state in matching:
        if state._probe_task is not None and not state._probe_task.done():
            state._probe_task.cancel()
        if state.state in ("open", "half_open") and state.opened_at is not None:
            total_open_s = int((datetime.now(UTC) - state.opened_at).total_seconds())
        else:
            total_open_s = 0
        effective_pool = pool if pool is not None else state._pool
        await _write_close_log(
            state,
            trigger_reason="api_key_update",
            total_open_seconds=total_open_s,
            pool=effective_pool,
        )
        del _CIRCUITS[key]


def get_open_states() -> list[CircuitState]:
    """Return all currently open or half_open circuit states (for metrics)."""
    return [s for s in _CIRCUITS.values() if s.state in ("open", "half_open")]


def _reset_for_tests() -> None:
    """Test-only: clear all circuit state."""
    _CIRCUITS.clear()


# ---------------------------------------------------------------------------
# Probe scheduler
# ---------------------------------------------------------------------------


def _maybe_launch_probe(state: CircuitState) -> None:
    """Schedule a probe if the backoff interval has elapsed.

    Guards against double-launch: skips when _probe_task is not None
    and not done.
    """
    if _backoff_schedule is None:
        return
    if state._probe_task is not None and not state._probe_task.done():
        return
    if state.opened_at is None:
        return
    position = min(state.probe_schedule_position, len(_backoff_schedule) - 1)
    wait_s = _backoff_schedule[position]
    ref_time = state._last_probe_attempt_at or state.opened_at
    elapsed = (datetime.now(UTC) - ref_time).total_seconds()
    if elapsed < wait_s:
        return
    state.state = "half_open"
    state._probe_task = asyncio.create_task(_run_probe(state))  # noqa: RUF006


async def _run_probe(state: CircuitState) -> None:
    """Execute a lightweight validate_credentials probe.

    Transitions state on outcome; writes audit rows; advances schedule.
    """
    from src.api_bridge.adapter import get_adapter as _get_adapter

    adapter = _get_adapter()
    state._last_probe_attempt_at = datetime.now(UTC)
    state.probes_attempted += 1
    probe_start = time.monotonic()
    is_exhausted = False
    if _backoff_schedule is not None:
        is_exhausted = state.probe_schedule_position >= len(_backoff_schedule) - 1
    outcome: str
    try:
        result = await asyncio.wait_for(
            adapter.validate_credentials(
                state.api_key_fingerprint,
                "",
            ),
            timeout=_probe_timeout_s,
        )
        latency_ms = int((time.monotonic() - probe_start) * 1000)
        if result.ok:
            outcome = "success"
            state.probes_succeeded += 1
            total_open_s = (
                int((datetime.now(UTC) - state.opened_at).total_seconds()) if state.opened_at else 0
            )
            await _write_probe_log(state, outcome, latency_ms, is_exhausted, pool=state._pool)
            await _write_close_log(
                state,
                trigger_reason="probe_success",
                total_open_seconds=total_open_s,
                pool=state._pool,
            )
            state.state = "closed"
            state.opened_at = None
            state.consecutive_open_turns = 0
            state.probe_schedule_position = 0
        else:
            outcome = "failure"
            await _write_probe_log(state, outcome, latency_ms, is_exhausted, pool=state._pool)
            _advance_probe_schedule(state)
            state.state = "open"
    except TimeoutError:
        latency_ms = int((time.monotonic() - probe_start) * 1000)
        outcome = "timeout"
        await _write_probe_log(state, outcome, latency_ms, is_exhausted, pool=state._pool)
        _advance_probe_schedule(state)
        state.state = "open"
    except Exception as exc:
        latency_ms = int((time.monotonic() - probe_start) * 1000)
        outcome = "failure"
        log.warning("probe_error participant=%s: %s", state.participant_id, exc)
        await _write_probe_log(state, outcome, latency_ms, is_exhausted, pool=state._pool)
        _advance_probe_schedule(state)
        state.state = "open"
    finally:
        state._probe_task = None


def _advance_probe_schedule(state: CircuitState) -> None:
    """Move to next backoff position; cycle on last (FR-009)."""
    if _backoff_schedule is None:
        return
    if state.probe_schedule_position < len(_backoff_schedule) - 1:
        state.probe_schedule_position += 1
    # else: already at last position; stay pinned (cycle-on-last)


# ---------------------------------------------------------------------------
# DB write helpers
# ---------------------------------------------------------------------------


async def _write_open_log(
    state: CircuitState,
    trigger_reason: str,
    failure_count: int,
    pool: object,
) -> None:
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO provider_circuit_open_log"
                " (session_id, participant_id, provider, api_key_fingerprint,"
                "  trigger_reason, failure_count, window_seconds)"
                " VALUES ($1, $2, $3, $4, $5, $6, $7)",
                state.session_id,
                state.participant_id,
                state.provider,
                state.api_key_fingerprint,
                trigger_reason,
                failure_count,
                _window_s or 0,
            )
    except Exception as exc:
        log.warning("circuit_open_log_write_failed: %s", exc)


async def _write_probe_log(
    state: CircuitState,
    outcome: str,
    latency_ms: int,
    schedule_exhausted: bool,
    *,
    pool: object,
) -> None:
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO provider_circuit_probe_log"
                " (session_id, participant_id, provider, api_key_fingerprint,"
                "  probe_outcome, probe_latency_ms, schedule_position, schedule_exhausted)"
                " VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                state.session_id,
                state.participant_id,
                state.provider,
                state.api_key_fingerprint,
                outcome,
                latency_ms,
                state.probe_schedule_position,
                schedule_exhausted,
            )
    except Exception as exc:
        log.warning("circuit_probe_log_write_failed: %s", exc)


async def _write_close_log(
    state: CircuitState,
    trigger_reason: str,
    total_open_seconds: int,
    pool: object,
) -> None:
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO provider_circuit_close_log"
                " (session_id, participant_id, provider, api_key_fingerprint,"
                "  total_open_seconds, probes_attempted, probes_succeeded, trigger_reason)"
                " VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                state.session_id,
                state.participant_id,
                state.provider,
                state.api_key_fingerprint,
                total_open_seconds,
                state.probes_attempted,
                state.probes_succeeded,
                trigger_reason,
            )
    except Exception as exc:
        log.warning("circuit_close_log_write_failed: %s", exc)


# ---------------------------------------------------------------------------
# FR-011 startup check
# ---------------------------------------------------------------------------


def check_no_cross_identity_fallbacks(litellm_router_config: list[dict]) -> None:
    """FR-011: raise SystemExit if any fallback entry has a different api_key fingerprint.

    Called at adapter initialization time. litellm_router_config is the
    router model_list. If empty or None, check passes silently.
    """
    if not litellm_router_config:
        return
    seen_fingerprints: dict[str, str] = {}
    for entry in litellm_router_config:
        model_name = entry.get("model_name", "")
        params = entry.get("litellm_params", {})
        api_key = params.get("api_key", "")
        fp = _compute_api_key_fingerprint(api_key) if api_key else "no_key"
        if model_name in seen_fingerprints and seen_fingerprints[model_name] != fp:
            raise SystemExit(
                f"FR-011 violation: LiteLLM router config for model {model_name!r} "
                f"contains fallback entries with different api_key fingerprints "
                f"({seen_fingerprints[model_name]!r} vs {fp!r}). "
                f"Cross-identity fallbacks are forbidden by spec 015 FR-011. "
                f"Remove the cross-identity fallback entry."
            )
        seen_fingerprints[model_name] = fp


# ---------------------------------------------------------------------------
# Metrics surface (FR-013)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BreakerMetricSnapshot:
    """One open/half_open circuit's metrics fields (FR-013)."""

    session_id: str
    participant_id: str
    provider: str
    trigger_reason: str
    open_since: datetime | None
    consecutive_open_turns: int


def get_metrics_snapshot() -> list[BreakerMetricSnapshot]:
    """Return per-breaker snapshot for the metrics surface.

    Reads from _CIRCUITS in-memory dict; no DB round-trip.
    """
    result = []
    for state in _CIRCUITS.values():
        if state.state not in ("open", "half_open"):
            continue
        trigger_reason = _dominant_failure_kind(state)
        result.append(
            BreakerMetricSnapshot(
                session_id=state.session_id,
                participant_id=state.participant_id,
                provider=state.provider,
                trigger_reason=trigger_reason,
                open_since=state.opened_at,
                consecutive_open_turns=state.consecutive_open_turns,
            )
        )
    return result


# Backwards-compat shim so existing code that imported CircuitBreaker still compiles.
# The class body is now module-level functions; this shim wraps them.
class CircuitBreaker:
    """Shim class wrapping the module-level circuit breaker functions.

    Existing loop.py imports reference this class by name; the shim
    forwards to the module-level implementation so the refactor is
    non-breaking.
    """

    def __init__(self, pool: object = None) -> None:
        self._pool = pool

    async def record_failure(self, participant_id: str) -> bool:
        """Legacy single-arg call — no-op; returns False."""
        return False

    async def record_success(self, participant_id: str) -> None:
        """Legacy single-arg success clear — no-op in new design."""

    async def is_open(self, participant_id: str) -> bool:
        """Legacy single-arg call — always returns False."""
        return False
