# SPDX-License-Identifier: AGPL-3.0-or-later

"""Signal-source adapters for the DMA controller (spec 014).

Four independent adapters — TurnRate, ConvergenceDerivative, QueueDepth,
DensityAnomaly — each implementing the Protocol contract from
specs/014-dynamic-mode-assignment/contracts/signal-source-interface.md.

Each adapter:
    - reports its env-var configuration via ``is_configured()``
    - reports its data-feed availability via ``is_available()``
    - samples an instantaneous value via ``sample()``
    - evaluates whether the rolling window crosses its threshold via
      ``evaluate(window)``

No cross-adapter coupling — the controller composes them via the Protocol
in dma_controller.py per FR-004 (per-signal independence).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class SignalSource(Protocol):
    """Adapter protocol for a single signal feed observed by the DMA controller.

    Per ``contracts/signal-source-interface.md``. Each adapter is independently
    testable, independently configurable, and independently disable-able.
    """

    name: str

    def is_configured(self) -> bool:
        """True iff this signal's threshold env var is set."""
        ...

    def is_available(self) -> bool:
        """True iff the underlying data feed has produced a measurement
        recently enough to use. Drives signal_source_unavailable events.
        """
        ...

    def sample(self) -> float | int | None:
        """Take an instantaneous sample of the signal's value.

        Returns None if unavailable; the controller treats that as
        a missing sample and does not append it to the ring buffer.
        """
        ...

    def threshold(self) -> float | int | None:
        """Configured threshold for this signal, parsed from its env var.

        Returns None if not configured.
        """
        ...

    def evaluate(self, window: list[float | int]) -> bool:
        """True iff the window of samples should trigger ENGAGE on this signal.

        For most signals this is ``mean(window) >= threshold``; for the
        convergence-derivative signal it's ``abs(window[-1] - window[0]) >=
        threshold``. Each adapter encapsulates its own evaluation rule.
        """
        ...


# ---------------------------------------------------------------------------
# Helpers shared by adapters
# ---------------------------------------------------------------------------


def _read_int_env(name: str) -> int | None:
    """Parse an integer env var or return None if unset/empty."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _read_float_env(name: str) -> float | None:
    """Parse a float env var or return None if unset/empty."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _mean(values: list[float | int]) -> float:
    """Numeric mean; 0.0 for empty windows so an unconfigured trigger never fires."""
    if not values:
        return 0.0
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# Concrete adapters
# ---------------------------------------------------------------------------


class TurnRateSignal:
    """``turn_rate`` signal source: turns/minute over the rolling window.

    Spec 014 §FR-003 (a) and contracts/signal-source-interface.md.
    Always available — turn count is observable from the loop callback.
    """

    name: str = "turn_rate"

    def __init__(self, sampler: Callable[[], int | None] | None = None) -> None:
        # Callable returning the most recent turns-in-prior-minute count.
        # Defaults to a no-op so the controller can construct the adapter
        # before the loop wires the per-turn callback.
        self._sampler = sampler or (lambda: None)

    def is_configured(self) -> bool:
        return _read_int_env("SACP_DMA_TURN_RATE_THRESHOLD_TPM") is not None

    def is_available(self) -> bool:
        return self._sampler() is not None

    def sample(self) -> int | None:
        return self._sampler()

    def threshold(self) -> int | None:
        return _read_int_env("SACP_DMA_TURN_RATE_THRESHOLD_TPM")

    def evaluate(self, window: list[float | int]) -> bool:
        thr = self.threshold()
        if thr is None or not window:
            return False
        return _mean(window) >= thr


class ConvergenceDerivativeSignal:
    """``convergence_derivative`` signal source.

    Reads ``ConvergenceDetector.last_similarity`` per research §2; the
    controller computes the per-window derivative magnitude on its own
    ring buffer and compares against the configured threshold.
    """

    name: str = "convergence_derivative"

    def __init__(self, similarity_provider: Callable[[], float | None] | None = None) -> None:
        # Callable returning the latest similarity score (or None pre-first-eval).
        self._provider = similarity_provider or (lambda: None)

    def is_configured(self) -> bool:
        return _read_float_env("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD") is not None

    def is_available(self) -> bool:
        return self._provider() is not None

    def sample(self) -> float | None:
        return self._provider()

    def threshold(self) -> float | None:
        return _read_float_env("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD")

    def evaluate(self, window: list[float | int]) -> bool:
        thr = self.threshold()
        if thr is None or len(window) < 2:
            return False
        return abs(window[-1] - window[0]) >= thr


class QueueDepthSignal:
    """``queue_depth`` signal source.

    Reads spec-013 batching's per-recipient queue sizes; spike-sensitive
    (uses ``max(window)`` rather than the mean). Inactive when batching
    is unconfigured (no scheduler) or in topology 5 (no humans).
    """

    name: str = "queue_depth"

    def __init__(
        self,
        depth_sampler: Callable[[], int | None] | None = None,
        availability: Callable[[], bool] | None = None,
    ) -> None:
        self._sampler = depth_sampler or (lambda: None)
        self._availability = availability or (lambda: False)

    def is_configured(self) -> bool:
        return _read_int_env("SACP_DMA_QUEUE_DEPTH_THRESHOLD") is not None

    def is_available(self) -> bool:
        return bool(self._availability()) and self._sampler() is not None

    def sample(self) -> int | None:
        return self._sampler()

    def threshold(self) -> int | None:
        return _read_int_env("SACP_DMA_QUEUE_DEPTH_THRESHOLD")

    def evaluate(self, window: list[float | int]) -> bool:
        thr = self.threshold()
        if thr is None or not window:
            return False
        return max(window) >= thr


class DensityAnomalySignal:
    """``density_anomaly`` signal source.

    Per research §1: counts ``convergence_log`` rows with
    ``tier='density_anomaly'`` produced in the prior minute (sliding count).
    Default heuristic; refine in Phase 6 if real session data shows the
    count is too noisy.
    """

    name: str = "density_anomaly"

    def __init__(self, count_sampler: Callable[[], int | None] | None = None) -> None:
        self._sampler = count_sampler or (lambda: None)

    def is_configured(self) -> bool:
        return _read_int_env("SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD") is not None

    def is_available(self) -> bool:
        # density.py's runtime contract is "always producing" — the only
        # unavailable case is "no measurements yet at session start".
        return self._sampler() is not None

    def sample(self) -> int | None:
        return self._sampler()

    def threshold(self) -> int | None:
        return _read_int_env("SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD")

    def evaluate(self, window: list[float | int]) -> bool:
        thr = self.threshold()
        if thr is None or not window:
            return False
        return _mean(window) >= thr
