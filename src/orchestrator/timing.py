# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-stage timing capture for V14 instrumentation.

Decorator-based wall-clock timing for turn-loop and security-pipeline
stages. Each turn calls `start_turn()` once before its first stage; each
decorated stage method records its duration into a `ContextVar`-backed
accumulator that survives `await` and `asyncio.create_task` boundaries.
The persist step calls `get_timings()` and writes the accumulated values
into `routing_log` (per 003 §FR-030) or `security_events.layer_duration_ms`
(per 007 §FR-020).

Per Constitution §12 V14 + spec 012 FR-007.

Usage:
    from src.orchestrator.timing import (
        get_timings, start_turn, with_stage_timing,
    )

    @with_stage_timing("route")
    async def _check_route(...):
        ...

    async def execute_turn():
        start_turn()
        await _check_route(...)
        # ... other stages ...
        timings = get_timings()
        # write timings["route"], timings["assemble"], ... into routing_log
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, ParamSpec, TypeVar

_T = TypeVar("_T")
_P = ParamSpec("_P")

_TIMINGS: ContextVar[dict[str, int] | None] = ContextVar("_TIMINGS", default=None)


def start_turn() -> None:
    """Reset the accumulator for a new turn boundary."""
    _TIMINGS.set({})


def reset() -> None:
    """Clear accumulator state (test cleanup)."""
    _TIMINGS.set(None)


def get_timings() -> dict[str, int]:
    """Read the current turn's accumulated stage timings.

    Returns an empty dict if no turn context is active. Returned dict is a
    snapshot — caller may freely mutate without affecting the accumulator.
    """
    timings = _TIMINGS.get()
    return dict(timings) if timings else {}


def record_stage(name: str, duration_ms: int) -> None:
    """Record one stage's duration into the current turn's accumulator.

    Adds to any existing duration for the same stage name (so retries or
    multiple invocations within a turn accumulate rather than overwrite).
    No-op if no turn context is active.
    """
    timings = _TIMINGS.get()
    if timings is None:
        return
    timings[name] = timings.get(name, 0) + duration_ms


def with_stage_timing(
    stage_name: str,
) -> Callable[[Callable[_P, Awaitable[_T]]], Callable[_P, Awaitable[_T]]]:
    """Async decorator: time the wrapped coroutine and record its duration.

    Records duration even if the wrapped function raises (the timing
    captures the work the stage attempted, including failed work).
    """

    def decorator(fn: Callable[_P, Awaitable[_T]]) -> Callable[_P, Awaitable[_T]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> _T:
            start = time.monotonic()
            try:
                return await fn(*args, **kwargs)
            finally:
                duration_ms = int((time.monotonic() - start) * 1000)
                record_stage(stage_name, duration_ms)

        return wrapper

    return decorator
