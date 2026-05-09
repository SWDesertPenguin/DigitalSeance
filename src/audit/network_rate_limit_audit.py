"""Network-layer rate-limit audit emission (spec 019 US3).

Per-(source_ip_keyed, minute_bucket) rejection coalescer + background
asyncio flush task that writes one admin_audit_log row per drained
bucket via the established append-only path (Constitution V9). Also
emits NON-coalesced source_ip_unresolvable rows per FR-012.

The admin_audit_log schema requires session_id / facilitator_id /
target_id NOT NULL (no schema delta per data-model.md "Schema additions:
None"). For network-layer rejections -- which run pre-auth and have no
session or facilitator context -- we use the sentinel string
``__network_layer__`` for both session_id and facilitator_id. The
unique action strings (``network_rate_limit_rejected``,
``source_ip_unresolvable``) plus the sentinel facilitator_id make
operator queries trivial: ``WHERE action = 'network_rate_limit_rejected'``
finds every infrastructure-tier row regardless of session.

Cross-refs:
- specs/019-network-rate-limiting/contracts/audit-events.md
- specs/019-network-rate-limiting/data-model.md
  (NetworkRateLimitRejectedRecord, SourceIPUnresolvableRecord)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel populated into NOT NULL admin_audit_log fields when the
# rejection has no session / facilitator context (network-layer events
# run pre-auth). Operators filter by action string; the sentinel keeps
# the row insertable without a schema delta.
_NETWORK_LAYER_SENTINEL: str = "__network_layer__"

# `endpoint_paths_seen` cap from contracts/audit-events.md "Row contract".
_PATHS_SEEN_CAP: int = 16

# Background flush cadence (seconds). Per research.md section6, drain at the
# top of each minute so a coalescing window closes before its row is
# written.
_FLUSH_INTERVAL_S: float = 60.0


@dataclass
class CoalesceState:
    """Per-(IP, minute_bucket) accumulator (data-model.md sectioncoalescing)."""

    minute_bucket: int
    first_rejected_at: float
    last_rejected_at: float
    rejection_count: int = 0
    endpoint_paths_seen: list[str] = field(default_factory=list)
    methods_seen: list[str] = field(default_factory=list)
    paths_truncated: bool = False
    limiter_window_remaining_s: float | None = None


class RejectionCoalescer:
    """In-memory accumulator for network_rate_limit_rejected rows."""

    def __init__(self) -> None:
        self._state: dict[tuple[str, int], CoalesceState] = {}

    def record_rejection(
        self,
        *,
        source_ip_keyed: str,
        path: str,
        method: str,
        remaining_s: float,
        now: float,
    ) -> None:
        """Update the (IP, minute) bucket; called per-rejection (FR-009)."""
        minute = int(now // 60)
        key = (source_ip_keyed, minute)
        state = self._state.get(key)
        if state is None:
            state = CoalesceState(
                minute_bucket=minute,
                first_rejected_at=now,
                last_rejected_at=now,
            )
            self._state[key] = state
        state.last_rejected_at = now
        state.rejection_count += 1
        state.limiter_window_remaining_s = float(remaining_s)
        _add_capped(state.endpoint_paths_seen, path, _PATHS_SEEN_CAP, state)
        _add_capped(state.methods_seen, method, _PATHS_SEEN_CAP, state)

    def drain_complete(self, now: float) -> list[tuple[str, CoalesceState]]:
        """Pop and return buckets whose minute is fully in the past."""
        cutoff = int(now // 60)
        ready: list[tuple[str, CoalesceState]] = []
        keys = list(self._state.keys())
        for key in keys:
            ip, minute = key
            if minute < cutoff:
                ready.append((ip, self._state.pop(key)))
        return ready

    def drain_all(self) -> list[tuple[str, CoalesceState]]:
        """Drain every bucket regardless of minute (shutdown / test helper)."""
        snapshot = list(self._state.items())
        self._state.clear()
        return [(ip_key[0], state) for ip_key, state in snapshot]

    def __len__(self) -> int:
        return len(self._state)


def _add_capped(seq: list[str], value: str, cap: int, state: CoalesceState) -> None:
    """Append ``value`` to ``seq`` if not present and below cap; flag truncation."""
    if value in seq:
        return
    if len(seq) >= cap:
        state.paths_truncated = True
        return
    seq.append(value)


# Module-level singleton -- request-path code calls record_rejection(...)
# without needing app.state plumbing. The flush task owns the lifecycle.
_COALESCER = RejectionCoalescer()


def record_rejection(
    *,
    source_ip_keyed: str,
    path: str,
    method: str,
    remaining_s: float,
    now: float,
) -> None:
    """Module-level shim -- request-path entry point (V14 budget: O(1))."""
    _COALESCER.record_rejection(
        source_ip_keyed=source_ip_keyed,
        path=path,
        method=method,
        remaining_s=remaining_s,
        now=now,
    )


def get_coalescer() -> RejectionCoalescer:
    """Test / flush-task entry point."""
    return _COALESCER


def reset_coalescer_for_tests() -> None:
    """Discard accumulated state -- for tests only."""
    _COALESCER.drain_all()


def serialize_rejection_payload(state: CoalesceState) -> str:
    """Render a CoalesceState as the admin_audit_log ``new_value`` JSON."""
    payload: dict[str, Any] = {
        "minute_bucket": state.minute_bucket,
        "first_rejected_at": _iso(state.first_rejected_at),
        "last_rejected_at": _iso(state.last_rejected_at),
        "rejection_count": state.rejection_count,
        "endpoint_paths_seen": list(state.endpoint_paths_seen),
        "methods_seen": list(state.methods_seen),
        "limiter_window_remaining_s": state.limiter_window_remaining_s,
    }
    if state.paths_truncated:
        payload["paths_truncated"] = True
    return json.dumps(payload, separators=(",", ":"))


def _iso(epoch_seconds: float) -> str:
    """ISO 8601 with UTC suffix."""
    return datetime.fromtimestamp(epoch_seconds, tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# source_ip_unresolvable -- NOT coalesced, one row per call
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceIPUnresolvableEvent:
    """Captured at FR-012 rejection time; flushed by the same task."""

    rejected_at: float
    path: str
    method: str
    reason: str


_UNRESOLVABLE_QUEUE: list[SourceIPUnresolvableEvent] = []


def emit_source_ip_unresolvable(
    *,
    path: str,
    method: str,
    reason: str,
    now: float,
) -> None:
    """Queue a SourceIPUnresolvableEvent for the flush task (FR-012)."""
    _UNRESOLVABLE_QUEUE.append(
        SourceIPUnresolvableEvent(
            rejected_at=now,
            path=path,
            method=method,
            reason=reason,
        ),
    )


def drain_unresolvable_queue() -> list[SourceIPUnresolvableEvent]:
    """Pop every queued unresolvable event (caller writes to DB)."""
    snapshot = list(_UNRESOLVABLE_QUEUE)
    _UNRESOLVABLE_QUEUE.clear()
    return snapshot


def reset_unresolvable_queue_for_tests() -> None:
    """Discard queued events -- for tests only."""
    _UNRESOLVABLE_QUEUE.clear()


def serialize_unresolvable_payload(event: SourceIPUnresolvableEvent) -> str:
    """Render a SourceIPUnresolvableEvent as the ``new_value`` JSON."""
    payload = {
        "rejected_at": _iso(event.rejected_at),
        "request_path": event.path,
        "request_method": event.method,
        "reason": event.reason,
    }
    return json.dumps(payload, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Background flush task -- runs OUTSIDE the request path (V14 budget)
# ---------------------------------------------------------------------------


_INSERT_AUDIT_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action,
         target_id, previous_value, new_value)
    VALUES ($1, $2, $3, $4, $5, $6)
"""


async def flush_once(
    pool: Any,
    *,
    now: float,
) -> int:
    """Flush all complete-minute coalesced buckets + queued unresolvables.

    Returns the number of rows written. Failures log via the existing
    audit-failure path and DO NOT propagate (V15 fail-closed: a flush
    failure must not block subsequent flushes or the request path).
    """
    written = 0
    for ip, state in _COALESCER.drain_complete(now):
        try:
            await _write_rejection_row(pool, ip=ip, state=state)
            written += 1
        except Exception:
            logger.exception("audit_flush_failed source_ip_keyed=%s", ip)
    for event in drain_unresolvable_queue():
        try:
            await _write_unresolvable_row(pool, event=event)
            written += 1
        except Exception:
            logger.exception("audit_flush_failed unresolvable path=%s", event.path)
    return written


async def _write_rejection_row(pool: Any, *, ip: str, state: CoalesceState) -> None:
    """Insert one network_rate_limit_rejected row via the append-only path."""
    payload = serialize_rejection_payload(state)
    async with pool.acquire() as conn:
        await conn.execute(
            _INSERT_AUDIT_SQL,
            _NETWORK_LAYER_SENTINEL,
            _NETWORK_LAYER_SENTINEL,
            "network_rate_limit_rejected",
            ip,
            None,
            payload,
        )


async def _write_unresolvable_row(pool: Any, *, event: SourceIPUnresolvableEvent) -> None:
    """Insert one source_ip_unresolvable row (target_id = sentinel; no IP)."""
    payload = serialize_unresolvable_payload(event)
    async with pool.acquire() as conn:
        await conn.execute(
            _INSERT_AUDIT_SQL,
            _NETWORK_LAYER_SENTINEL,
            _NETWORK_LAYER_SENTINEL,
            "source_ip_unresolvable",
            _NETWORK_LAYER_SENTINEL,
            None,
            payload,
        )


async def run_flush_loop(pool: Any, *, interval_s: float = _FLUSH_INTERVAL_S) -> None:
    """Background asyncio task -- drain + write once per interval (research.md section6)."""
    import time as _time

    while True:
        await asyncio.sleep(interval_s)
        try:
            await flush_once(pool, now=_time.time())
        except Exception:
            logger.exception("audit_flush_loop_iteration_failed")


__all__ = [
    "CoalesceState",
    "RejectionCoalescer",
    "SourceIPUnresolvableEvent",
    "drain_unresolvable_queue",
    "emit_source_ip_unresolvable",
    "flush_once",
    "get_coalescer",
    "record_rejection",
    "reset_coalescer_for_tests",
    "reset_unresolvable_queue_for_tests",
    "run_flush_loop",
    "serialize_rejection_payload",
    "serialize_unresolvable_payload",
]
