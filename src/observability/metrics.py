# SPDX-License-Identifier: AGPL-3.0-or-later

"""Prometheus metric surface -- public API for spec 016 (replaces pre-016 stub).

This module exposes the same external call surface that spec 019 and spec 015
pinned so their call sites need zero changes:

    sacp_rate_limit_rejection_total.labels(...).inc()
    sacp_rate_limit_rejection_total.get_sample_value({...})
    sacp_rate_limit_rejection_total.samples()
    increment_network_rate_limit_rejection()
    reset_for_tests()
    get_circuit_breaker_metrics()

The internals now delegate to real ``prometheus_client`` objects via
``src.observability.metrics_registry``.  The fake ``_CounterFamily`` /
``_BoundCounter`` classes are replaced; the privacy guards and label
contract from the pre-016 stub are preserved in the wrapper layer.

Cardinality contract (FR-010 + SC-009 + contracts/metrics.md):
- Label set for sacp_rate_limit_rejection_total is exactly
  ``{endpoint_class, exempt_match}``.
- ``endpoint_class`` in {``network_per_ip``, ``app_layer_per_participant``}.
- ``exempt_match`` in {``true``, ``false``}.
- NO source IP, query string, headers, body content, or PII appears as a label.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from src.observability.metrics_registry import (
    REGISTRY as REGISTRY,  # re-exported for /metrics endpoint
)
from src.observability.metrics_registry import (
    get_registry,
    inc_rate_limit_rejection,
    reset_registry_for_tests,
)

# ---------------------------------------------------------------------------
# Privacy-contract enforcement (preserved from pre-016 stub)
# ---------------------------------------------------------------------------

_ALLOWED_ENDPOINT_CLASSES = frozenset({"network_per_ip", "app_layer_per_participant"})
_ALLOWED_EXEMPT_MATCH = frozenset({"true", "false"})
_REQUIRED_LABELS = frozenset({"endpoint_class", "exempt_match"})


def _assert_labels(labels: dict[str, str]) -> None:
    """Enforce the SC-009 privacy contract -- exactly two labels, allowed values."""
    keys = frozenset(labels.keys())
    if keys != _REQUIRED_LABELS:
        raise ValueError(
            f"sacp_rate_limit_rejection_total label set must be exactly "
            f"{sorted(_REQUIRED_LABELS)}; got {sorted(keys)}",
        )
    endpoint_class = labels["endpoint_class"]
    if endpoint_class not in _ALLOWED_ENDPOINT_CLASSES:
        raise ValueError(
            f"endpoint_class must be one of {sorted(_ALLOWED_ENDPOINT_CLASSES)}; "
            f"got {endpoint_class!r}",
        )
    exempt_match = labels["exempt_match"]
    if exempt_match not in _ALLOWED_EXEMPT_MATCH:
        raise ValueError(
            f"exempt_match must be 'true' or 'false'; got {exempt_match!r}",
        )


# ---------------------------------------------------------------------------
# MetricSample -- preserved for spec 019 test compatibility
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricSample:
    """One emitted (labels -> value) pair for a counter."""

    name: str
    labels: dict[str, str]
    value: float


# ---------------------------------------------------------------------------
# _BoundCounter wrapper -- preserves spec 019 .inc() call site
# ---------------------------------------------------------------------------


class _BoundCounter:
    """Handle returned by ``_RateLimitCounterFacade.labels(**kw)``."""

    def __init__(self, labels: dict[str, str]) -> None:
        self._labels = labels

    def inc(self, amount: float = 1.0) -> None:
        """Increment the underlying prometheus_client Counter."""
        inc_rate_limit_rejection(
            endpoint_class=self._labels["endpoint_class"],
            exempt_match=self._labels["exempt_match"],
        )
        # If amount != 1 we call inc() ``amount`` more times -- this is
        # unconventional but preserves exact counter semantics for callers
        # that pass a custom amount.  The rate-limit path always uses default 1.
        for _ in range(int(amount) - 1):
            inc_rate_limit_rejection(
                endpoint_class=self._labels["endpoint_class"],
                exempt_match=self._labels["exempt_match"],
            )


# ---------------------------------------------------------------------------
# _RateLimitCounterFacade -- preserves spec 019 test introspection surface
# ---------------------------------------------------------------------------


class _RateLimitCounterFacade:
    """Facade over the real prometheus_client Counter for sacp_rate_limit_rejection_total.

    Exposes the pre-016 stub API:
      .labels(**kw) -> _BoundCounter
      .get_sample_value({...}) -> float | None
      .samples() -> Iterator[MetricSample]
      .reset() -> None (test helper)
    """

    # prometheus_client stores counters under the family name WITHOUT _total,
    # but emits samples with the _total suffix.  Both names are used here.
    _FAMILY_NAME = "sacp_rate_limit_rejection"
    _TOTAL_NAME = "sacp_rate_limit_rejection_total"

    @property
    def name(self) -> str:
        return self._TOTAL_NAME

    def labels(self, **kwargs: str) -> _BoundCounter:
        """Validate the label set then return a bound handle."""
        _assert_labels(kwargs)
        return _BoundCounter(dict(kwargs))

    def get_sample_value(self, labels: dict[str, str]) -> float | None:
        """Return the current value for an exact label set; None if not found.

        Reads directly from the prometheus_client registry's collected samples.
        Uses get_registry() so post-reset references are always current.
        """
        _assert_labels(labels)
        for metric in get_registry().collect():
            # metric.name is the family name (without _total suffix)
            if metric.name != self._FAMILY_NAME:
                continue
            for sample in metric.samples:
                # Only match the _total sample (not _created)
                if sample.name != self._TOTAL_NAME:
                    continue
                if sample.labels == labels:
                    return sample.value
        return None

    def samples(self) -> Iterator[MetricSample]:
        """Iterate every (labels -> value) pair currently stored."""
        for metric in get_registry().collect():
            if metric.name != self._FAMILY_NAME:
                continue
            for sample in metric.samples:
                # Only yield the _total samples (not _created)
                if sample.name != self._TOTAL_NAME:
                    continue
                if sample.labels:
                    yield MetricSample(
                        name=self.name,
                        labels=dict(sample.labels),
                        value=sample.value,
                    )

    def reset(self) -> None:
        """Test helper -- discard all counter values by rebuilding the registry."""
        reset_registry_for_tests()

        # After reset_registry_for_tests() the module-global REGISTRY is
        # replaced.  Re-import so our facade reads the fresh registry on the
        # next call.  This is safe because REGISTRY is module-level in
        # metrics_registry and we re-import it lazily on each access below.


# Module-level facade instance -- drop-in replacement for the pre-016 stub
sacp_rate_limit_rejection_total: _RateLimitCounterFacade = _RateLimitCounterFacade()


# ---------------------------------------------------------------------------
# Spec 015 circuit breaker metrics (FR-013) -- unchanged from pre-016 stub
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CircuitBreakerMetrics:
    """Aggregate circuit-breaker state snapshot per FR-013.

    ``open_count`` is the number of currently open or half_open circuits.
    ``open_since_by_participant`` maps (session_id, participant_id) to
    the ISO-format open-since timestamp. ``trigger_reason_counts`` maps
    trigger_reason string to count of currently-open circuits with that reason.
    """

    open_count: int
    open_since_by_participant: dict[tuple[str, str], str]
    trigger_reason_counts: dict[str, int]


def get_circuit_breaker_metrics() -> CircuitBreakerMetrics:
    """Return a live snapshot of circuit breaker state for FR-013.

    Reads from the in-memory _CIRCUITS dict (no DB round-trip).
    """
    from src.orchestrator.circuit_breaker import get_metrics_snapshot

    snapshots = get_metrics_snapshot()
    open_since: dict[tuple[str, str], str] = {}
    reason_counts: dict[str, int] = {}
    for snap in snapshots:
        key = (snap.session_id, snap.participant_id)
        if snap.open_since is not None:
            open_since[key] = snap.open_since.isoformat()
        reason_counts[snap.trigger_reason] = reason_counts.get(snap.trigger_reason, 0) + 1
    return CircuitBreakerMetrics(
        open_count=len(snapshots),
        open_since_by_participant=open_since,
        trigger_reason_counts=reason_counts,
    )


# ---------------------------------------------------------------------------
# Public wrappers -- spec 019 call site API
# ---------------------------------------------------------------------------


def increment_network_rate_limit_rejection() -> None:
    """Spec 019 rejection branch helper (FR-010 + contracts/metrics.md)."""
    sacp_rate_limit_rejection_total.labels(
        endpoint_class="network_per_ip",
        exempt_match="false",
    ).inc()


def reset_for_tests() -> None:
    """Test helper -- discard all counter values."""
    sacp_rate_limit_rejection_total.reset()


__all__ = [
    "REGISTRY",
    "CircuitBreakerMetrics",
    "MetricSample",
    "get_circuit_breaker_metrics",
    "increment_network_rate_limit_rejection",
    "reset_for_tests",
    "sacp_rate_limit_rejection_total",
]
