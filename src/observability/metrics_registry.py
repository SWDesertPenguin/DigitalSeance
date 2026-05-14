# SPDX-License-Identifier: AGPL-3.0-or-later

"""Prometheus CollectorRegistry + all metric families for spec 016.

This module owns the single process-scope ``REGISTRY`` and the six
metric families.  The session-eviction tracker (``MetricsEvictionTracker``)
removes session-scoped label series within ``SACP_METRICS_SESSION_GRACE_S``
after a session ends (FR-006 / SC-003).

Cardinality contract (FR-005):
- Non-session-scoped counters: bounded fixed enumerations only.
- Session-scoped: bounded by active_sessions x participants x per-family
  label combinations.  Eviction fires via ``schedule_session_eviction``.

Privacy contract (FR-004):
- No label may carry: message content, system prompt, API key, model name,
  IP address, user-agent, or request URL.
- ``participant_id_hash`` is the first 8 hex chars of SHA-256(participant_id).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections import defaultdict
from typing import Any

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Isolated registry (keeps spec 016 metrics out of the default global registry
# so test isolation is clean and the /metrics endpoint only emits SACP metrics)
# ---------------------------------------------------------------------------

REGISTRY: CollectorRegistry = CollectorRegistry()

# ---------------------------------------------------------------------------
# Metric families
# ---------------------------------------------------------------------------

# US3 -- rate-limit rejections (spec 019 wires this; spec 016 owns the counter)
_rate_limit_rejection_total: Counter = Counter(
    "sacp_rate_limit_rejection_total",
    "Rate-limit rejections by class",
    ["endpoint_class", "exempt_match"],
    registry=REGISTRY,
)

# US1 -- participant token spend
_participant_tokens_total: Counter = Counter(
    "sacp_participant_tokens_total",
    "Provider token usage per session participant and direction",
    ["session_id", "participant_id_hash", "direction"],
    registry=REGISTRY,
)

# US1 -- participant cost spend
_participant_cost_usd_total: Counter = Counter(
    "sacp_participant_cost_usd_total",
    "Provider cost in USD per session participant",
    ["session_id", "participant_id_hash"],
    registry=REGISTRY,
)

# US2 -- provider health (not session-scoped; bounded enums)
_provider_request_total: Counter = Counter(
    "sacp_provider_request_total",
    "Provider dispatch requests by kind and outcome",
    ["provider_kind", "outcome"],
    registry=REGISTRY,
)

# US2 -- convergence quality (session-scoped gauge)
_session_convergence_similarity: Gauge = Gauge(
    "sacp_session_convergence_similarity",
    "Last convergence similarity score for a session (0=diverged, 1=converged)",
    ["session_id"],
    registry=REGISTRY,
)

# US3 -- routing decisions (session-scoped counter)
_routing_decision_total: Counter = Counter(
    "sacp_routing_decision_total",
    "Routing decisions per session and decision class",
    ["session_id", "routing_mode", "skip_reason"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Privacy helpers
# ---------------------------------------------------------------------------


def participant_id_hash(participant_id: str) -> str:
    """First 8 hex chars of SHA-256(participant_id) -- privacy-safe label value."""
    return hashlib.sha256(participant_id.encode()).hexdigest()[:8]


def normalize_provider_kind(provider: str | None) -> str:
    """Normalize provider string to bounded ``provider_kind`` label value.

    Returns ``litellm``, ``mock``, or ``other``.
    """
    if not provider:
        return "other"
    lower = provider.lower()
    if lower in ("litellm", "mock"):
        return lower
    return "other"


# ---------------------------------------------------------------------------
# Public increment helpers
# ---------------------------------------------------------------------------


def inc_rate_limit_rejection(*, endpoint_class: str, exempt_match: str) -> None:
    """Increment sacp_rate_limit_rejection_total with validated labels."""
    _rate_limit_rejection_total.labels(
        endpoint_class=endpoint_class,
        exempt_match=exempt_match,
    ).inc()


def inc_participant_tokens(
    *,
    session_id: str,
    participant_id: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Increment token counters for a participant turn."""
    pid_hash = participant_id_hash(participant_id)
    if prompt_tokens > 0:
        _participant_tokens_total.labels(
            session_id=session_id,
            participant_id_hash=pid_hash,
            direction="prompt",
        ).inc(prompt_tokens)
        _tracker.register(session_id, "tokens", (session_id, pid_hash, "prompt"))
    if completion_tokens > 0:
        _participant_tokens_total.labels(
            session_id=session_id,
            participant_id_hash=pid_hash,
            direction="completion",
        ).inc(completion_tokens)
        _tracker.register(session_id, "tokens", (session_id, pid_hash, "completion"))


def inc_participant_cost(
    *,
    session_id: str,
    participant_id: str,
    cost_usd: float,
) -> None:
    """Increment cost counter for a participant turn."""
    if cost_usd <= 0:
        return
    pid_hash = participant_id_hash(participant_id)
    _participant_cost_usd_total.labels(
        session_id=session_id,
        participant_id_hash=pid_hash,
    ).inc(cost_usd)
    _tracker.register(session_id, "cost", (session_id, pid_hash))


def inc_provider_request(*, provider_kind: str, outcome: str) -> None:
    """Increment provider request counter (not session-scoped)."""
    _provider_request_total.labels(
        provider_kind=provider_kind,
        outcome=outcome,
    ).inc()


def set_convergence_similarity(*, session_id: str, similarity: float) -> None:
    """Set convergence gauge for a session."""
    _session_convergence_similarity.labels(session_id=session_id).set(similarity)
    _tracker.register(session_id, "convergence", (session_id,))


def inc_routing_decision(
    *,
    session_id: str,
    routing_mode: str,
    skip_reason: str,
) -> None:
    """Increment routing decision counter for a session."""
    _routing_decision_total.labels(
        session_id=session_id,
        routing_mode=routing_mode,
        skip_reason=skip_reason,
    ).inc()
    _tracker.register(session_id, "routing", (session_id, routing_mode, skip_reason))


# ---------------------------------------------------------------------------
# Session eviction
# ---------------------------------------------------------------------------


class MetricsEvictionTracker:
    """Track per-session registered label tuples for eviction.

    Each session accumulates the label tuples it has registered across
    all session-scoped metric families.  On eviction, the tracker iterates
    and calls ``.remove(*labelvalues)`` on each family for each stored tuple.
    """

    def __init__(self) -> None:
        # session_id -> family_key -> set of label tuples
        self._state: dict[str, dict[str, set[tuple[str, ...]]]] = defaultdict(
            lambda: defaultdict(set)
        )

    def register(self, session_id: str, family_key: str, labelvalues: tuple[str, ...]) -> None:
        """Record that ``labelvalues`` have been set for this session/family."""
        self._state[session_id][family_key].add(labelvalues)

    def evict(self, session_id: str) -> None:
        """Remove all metric series for ``session_id`` from the registry."""
        families = self._state.pop(session_id, {})
        for family_key, labelsets in families.items():
            metric = _FAMILY_BY_KEY.get(family_key)
            if metric is None:
                continue
            for labelvalues in labelsets:
                try:
                    metric.remove(*labelvalues)
                except Exception as exc:  # noqa: BLE001
                    log.debug(
                        "metrics_eviction_remove_failed family=%s labels=%s err=%s",
                        family_key,
                        labelvalues,
                        exc,
                    )
        log.debug("metrics_eviction_complete session=%s", session_id)


# Map family_key -> prometheus_client object for .remove() dispatch
_FAMILY_BY_KEY: dict[str, Any] = {
    "tokens": _participant_tokens_total,
    "cost": _participant_cost_usd_total,
    "convergence": _session_convergence_similarity,
    "routing": _routing_decision_total,
}

_tracker = MetricsEvictionTracker()


def _default_grace_s() -> int:
    """Read SACP_METRICS_SESSION_GRACE_S; default 30."""
    raw = os.environ.get("SACP_METRICS_SESSION_GRACE_S", "30")
    try:
        return int(raw)
    except ValueError:
        return 30


def schedule_session_eviction(session_id: str, grace_s: int | None = None) -> None:
    """Schedule eviction of session metric series after ``grace_s`` seconds.

    If no event loop is running (e.g., synchronous tests), eviction fires
    immediately.  In production the asyncio loop is always running so
    ``call_later`` fires in the background after the grace window.
    """
    delay = grace_s if grace_s is not None else _default_grace_s()
    try:
        loop = asyncio.get_running_loop()
        loop.call_later(delay, _tracker.evict, session_id)
    except RuntimeError:
        # No running loop -- evict synchronously (test / CLI path)
        _tracker.evict(session_id)


def evict_session(session_id: str) -> None:
    """Evict immediately (for testing or synchronous teardown paths)."""
    _tracker.evict(session_id)


def get_registry() -> CollectorRegistry:
    """Return the current REGISTRY (re-read after reset_registry_for_tests).

    Tests MUST call this rather than importing REGISTRY at module level,
    because reset_registry_for_tests() replaces the module-global and
    top-level imports hold stale references.
    """
    return REGISTRY


def _build_non_session_counters(reg: CollectorRegistry) -> tuple[Counter, Counter]:
    """Create the two non-session-scoped counters on ``reg``."""
    rate_limit = Counter(
        "sacp_rate_limit_rejection_total",
        "Rate-limit rejections by class",
        ["endpoint_class", "exempt_match"],
        registry=reg,
    )
    provider = Counter(
        "sacp_provider_request_total",
        "Provider dispatch requests by kind and outcome",
        ["provider_kind", "outcome"],
        registry=reg,
    )
    return rate_limit, provider


def _build_session_counters(reg: CollectorRegistry) -> tuple[Counter, Counter, Gauge, Counter]:
    """Create the four session-scoped metric families on ``reg``."""
    tokens = Counter(
        "sacp_participant_tokens_total",
        "Provider token usage per session participant and direction",
        ["session_id", "participant_id_hash", "direction"],
        registry=reg,
    )
    cost = Counter(
        "sacp_participant_cost_usd_total",
        "Provider cost in USD per session participant",
        ["session_id", "participant_id_hash"],
        registry=reg,
    )
    convergence = Gauge(
        "sacp_session_convergence_similarity",
        "Last convergence similarity score for a session (0=diverged, 1=converged)",
        ["session_id"],
        registry=reg,
    )
    routing = Counter(
        "sacp_routing_decision_total",
        "Routing decisions per session and decision class",
        ["session_id", "routing_mode", "skip_reason"],
        registry=reg,
    )
    return tokens, cost, convergence, routing


def reset_registry_for_tests() -> None:
    """Test helper: re-create all metric objects on a fresh registry.

    Clears the eviction tracker and rebuilds every Counter/Gauge so test
    isolation is complete.  NOT called in production.
    """
    global REGISTRY  # noqa: PLW0603
    global _rate_limit_rejection_total  # noqa: PLW0603
    global _participant_tokens_total  # noqa: PLW0603
    global _participant_cost_usd_total  # noqa: PLW0603
    global _provider_request_total  # noqa: PLW0603
    global _session_convergence_similarity  # noqa: PLW0603
    global _routing_decision_total  # noqa: PLW0603

    REGISTRY = CollectorRegistry()
    _rate_limit_rejection_total, _provider_request_total = _build_non_session_counters(REGISTRY)
    (
        _participant_tokens_total,
        _participant_cost_usd_total,
        _session_convergence_similarity,
        _routing_decision_total,
    ) = _build_session_counters(REGISTRY)  # noqa: E501
    _FAMILY_BY_KEY.update(
        tokens=_participant_tokens_total,
        cost=_participant_cost_usd_total,
        convergence=_session_convergence_similarity,
        routing=_routing_decision_total,
    )
    _tracker._state.clear()


__all__ = [
    "REGISTRY",
    "MetricsEvictionTracker",
    "evict_session",
    "get_registry",
    "inc_participant_cost",
    "inc_participant_tokens",
    "inc_provider_request",
    "inc_rate_limit_rejection",
    "inc_routing_decision",
    "normalize_provider_kind",
    "participant_id_hash",
    "reset_registry_for_tests",
    "schedule_session_eviction",
    "set_convergence_similarity",
]
