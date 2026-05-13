# SPDX-License-Identifier: AGPL-3.0-or-later

"""Prometheus-shaped counter surface (spec 019 -- pre-spec-016 stub).

Spec 016's full prometheus_client integration has not landed yet, so
this module provides a minimal in-process counter shape with the exact
label set the spec 019 contract pins (``endpoint_class``,
``exempt_match``). When spec 016 ships its real counter, swap the
internals here without changing call sites.

Cardinality contract (FR-010 + SC-009 + contracts/metrics.md):
- Label set is exactly ``{endpoint_class, exempt_match}``.
- ``endpoint_class`` is a string enum; spec 019 emits only
  ``"network_per_ip"``. ``"app_layer_per_participant"`` is reserved.
- ``exempt_match`` is the string boolean ``"true"`` / ``"false"``.
- NO source IP, query string, headers, body content, or any other
  PII / per-request attribute appears as a label.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass

# Allowed values for the two labels -- enforced by ``_assert_labels``.
_ALLOWED_ENDPOINT_CLASSES = frozenset({"network_per_ip", "app_layer_per_participant"})
_ALLOWED_EXEMPT_MATCH = frozenset({"true", "false"})

# Required label set (anything else is a privacy contract violation).
_REQUIRED_LABELS = frozenset({"endpoint_class", "exempt_match"})


@dataclass(frozen=True)
class MetricSample:
    """One emitted (labels -> value) pair for a counter."""

    name: str
    labels: dict[str, str]
    value: float


class _CounterFamily:
    """Minimal Prometheus-counter facade scoped to spec 019's surface."""

    def __init__(self, name: str, help_text: str) -> None:
        self.name = name
        self.help_text = help_text
        self._values: dict[tuple[tuple[str, str], ...], float] = defaultdict(float)

    def labels(self, **kwargs: str) -> _BoundCounter:
        """Bind labels and return a handle with ``.inc()``."""
        _assert_labels(kwargs)
        key = tuple(sorted(kwargs.items()))
        return _BoundCounter(self, key, dict(kwargs))

    def get_sample_value(self, labels: dict[str, str]) -> float | None:
        """Lookup the current value for an exact label set; None if absent."""
        _assert_labels(labels)
        key = tuple(sorted(labels.items()))
        return self._values.get(key)

    def samples(self) -> Iterator[MetricSample]:
        """Iterate every (labels -> value) pair currently stored."""
        for key, value in self._values.items():
            yield MetricSample(name=self.name, labels=dict(key), value=value)

    def reset(self) -> None:
        """Test helper -- discard all stored values."""
        self._values.clear()


class _BoundCounter:
    """Result of ``family.labels(**kw)`` -- only ``.inc()`` is exposed."""

    def __init__(
        self,
        family: _CounterFamily,
        key: tuple[tuple[str, str], ...],
        labels: dict[str, str],
    ) -> None:
        self._family = family
        self._key = key
        self.labels = labels

    def inc(self, amount: float = 1.0) -> None:
        """Increment the bound counter by ``amount`` (default 1)."""
        self._family._values[self._key] += amount


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


# Module-level counter -- spec 016 owns the canonical name.
sacp_rate_limit_rejection_total = _CounterFamily(
    name="sacp_rate_limit_rejection_total",
    help_text="Rate-limit rejections by class",
)


# ---------------------------------------------------------------------------
# Spec 015 circuit breaker metrics (FR-013)
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
    "CircuitBreakerMetrics",
    "MetricSample",
    "get_circuit_breaker_metrics",
    "increment_network_rate_limit_rejection",
    "reset_for_tests",
    "sacp_rate_limit_rejection_total",
]
