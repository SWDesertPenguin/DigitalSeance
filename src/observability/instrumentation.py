# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-stage latency instrumentation for V14 performance budgets.

Spec 022 Performance Budgets contribute four observable stage timings:

- ``detection_events.page_load_ms`` — initial GET fetch (target P95 500ms
  for 1000 events).
- ``detection_events.resurface_same_instance_ms`` — POST resurface when
  the facilitator's WS is bound to the same orchestrator process
  (target P95 200ms).
- ``detection_events.resurface_cross_instance_ms`` — POST resurface when
  the facilitator's WS is bound to a different process (NOTIFY hop;
  target P95 500ms).
- ``detection_events.ws_push_ms`` — WS payload assembly + send latency
  for the live-update path (target P95 100ms).

The helper here keeps the call sites uniform: an async context manager
that captures ``time.perf_counter`` deltas and emits a structured log
line on exit. Spec 016's Prometheus integration is the eventual landing
spot; until then the structured log is the budget-enforcement signal
(consumed by scripts/check_perf_budgets.py and the daily access-log
sweep).

Usage:

.. code-block:: python

    from src.observability.instrumentation import instrument_stage

    async with instrument_stage(
        "detection_events.page_load",
        session_id=session_id,
    ) as stage:
        rows = await log_repo.get_detection_events_page(session_id)
        stage["row_count"] = len(rows)

The helper is intentionally minimal — no global state, no thread-locals.
Tests can patch the ``_logger`` attribute to capture emitted records.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def instrument_stage(
    stage_name: str,
    **base_labels: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Record perf-counter delta for one V14 stage and emit a structured log.

    ``stage_name`` is the dotted budget identifier (e.g.,
    ``detection_events.page_load``). ``base_labels`` are tacked onto the
    emitted record's ``extra`` dict so log consumers can slice by session,
    participant, etc. Callers can mutate the yielded dict to add further
    labels before the context exits.

    A non-success exit still emits the timing — partial work still costs
    perf budget — but adds an ``exception`` field so post-hoc analysis can
    separate happy-path from error-path latencies.
    """
    labels: dict[str, Any] = dict(base_labels)
    start = time.perf_counter()
    failure: BaseException | None = None
    try:
        yield labels
    except BaseException as exc:  # noqa: BLE001 — re-raise after logging
        failure = exc
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        record: dict[str, Any] = {
            "stage": stage_name,
            "elapsed_ms": round(elapsed_ms, 3),
            **labels,
        }
        if failure is not None:
            record["exception"] = type(failure).__name__
        # WARN when an exception was raised so operators see budget regressions
        # on the error path. Happy-path emission stays at DEBUG to avoid log
        # spam (production access-log consumers sample DEBUG separately).
        if failure is not None:
            _logger.warning("%s.elapsed_ms", stage_name, extra=record)
        else:
            _logger.debug("%s.elapsed_ms", stage_name, extra=record)


__all__ = ["instrument_stage"]
