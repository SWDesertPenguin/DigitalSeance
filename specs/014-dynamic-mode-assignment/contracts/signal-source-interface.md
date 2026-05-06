# Contract: signal-source adapter interface

Every signal source feeds the controller via a uniform adapter contract. Adapters live in `src/orchestrator/dma_signals.py` and are registered with the controller during `start()`.

## Adapter Protocol

```python
from typing import Protocol


class SignalSource(Protocol):
    """Adapter for a single signal feed observed by the DMA controller."""

    name: str  # canonical signal name, used in audit events and env-var routing

    def is_configured(self) -> bool:
        """True iff this signal's threshold env var is set."""

    def is_available(self) -> bool:
        """True iff the underlying data feed has produced a measurement
        recently enough to use. Drives signal_source_unavailable events.
        """

    def sample(self) -> float | int | None:
        """Take an instantaneous sample of the signal's value.
        Returns None if unavailable; the controller treats that as
        a missing sample and does not append it to the ring buffer.
        """

    def threshold(self) -> float | int | None:
        """Configured threshold for this signal, parsed from its env var.
        Returns None if not configured.
        """

    def evaluate(self, window: list[float | int]) -> bool:
        """True iff the window of samples should trigger ENGAGE on this signal.
        For most signals this is `mean(window) >= threshold`; for the
        convergence-derivative signal it's `abs(window[-1] - window[0]) >= threshold`.
        Each adapter encapsulates its own evaluation rule.
        """
```

## Four concrete adapters

### `TurnRateSignal`

- `name = "turn_rate"`
- `is_configured`: `SACP_DMA_TURN_RATE_THRESHOLD_TPM` is set.
- `is_available`: always True (turn count is observable from the loop's per-turn callback).
- `sample`: turns observed in the prior minute (sliding count).
- `threshold`: parsed integer (1–600).
- `evaluate`: `mean(window) >= threshold`.

### `ConvergenceDerivativeSignal`

- `name = "convergence_derivative"`
- `is_configured`: `SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD` is set.
- `is_available`: `ConvergenceEngine.last_similarity is not None` (per [research.md §2](../research.md)).
- `sample`: `engine.last_similarity` (the most recent value; the per-window derivative is computed by the controller from the buffer).
- `threshold`: parsed float (`(0.0, 1.0]`).
- `evaluate`: `abs(window[-1] - window[0]) >= threshold` (per-window absolute derivative magnitude).

### `QueueDepthSignal`

- `name = "queue_depth"`
- `is_configured`: `SACP_DMA_QUEUE_DEPTH_THRESHOLD` is set.
- `is_available`: spec-013 batching is configured for the session AND has at least one human recipient queue. Inactive in topology 5 (no humans).
- `sample`: current depth across all per-recipient queues for the session.
- `threshold`: parsed integer (1–1000).
- `evaluate`: `max(window) >= threshold` (the spike, not the mean — short bursts of queue depth are the failure mode this signal catches).

### `DensityAnomalySignal`

- `name = "density_anomaly"`
- `is_configured`: `SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD` is set.
- `is_available`: `density.py` is producing measurements (always True in practice; existing module's runtime contract).
- `sample`: count of `density_anomaly`-flagged turns in the prior minute (sliding count from `convergence_log`).
- `threshold`: parsed integer (1–60).
- `evaluate`: `mean(window) >= threshold` (per-window rate).

## Independence guarantee

A signal source whose `is_configured()` returns False MUST NOT contribute to controller decisions. The controller iterates only over configured sources at each cycle, satisfying spec FR-004's "absent, not zero" semantic.

A signal source whose `is_available()` returns False contributes nothing this cycle and may emit one rate-limited `signal_source_unavailable` audit event per dwell window per session.

## Per-signal cost capture

Each adapter's `sample()` and `evaluate()` calls run inside `@with_stage_timing` (per V14). The stage name is `dma_signal_<adapter.name>_ms`. This lets operators identify a regressing signal source by its cost profile (FR-012).

## No cross-signal coupling

Adapters do not call each other. The controller's `evaluate_cycle()` collects each adapter's `evaluate(window)` boolean independently and applies FR-009's asymmetry rule (ANY True → ENGAGE; ALL False during dwell → DISENGAGE). This keeps signal sources independently testable (US3).
