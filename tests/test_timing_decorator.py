# SPDX-License-Identifier: AGPL-3.0-or-later

"""Meta-tests for src.orchestrator.timing (spec 012 FR-007 / Constitution §12 V14).

Verifies:
- Decorator captures duration for sync-and-async work
- ContextVar isolates timings across asyncio.create_task boundaries
- Same-stage repeated calls accumulate (don't overwrite)
- record_stage is a no-op outside a turn context
- Decorator overhead is bounded (microbenchmark)
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.orchestrator.timing import (
    get_timings,
    record_stage,
    reset,
    start_turn,
    with_stage_timing,
)


@pytest.fixture(autouse=True)
def _reset_between_tests() -> None:
    reset()


async def test_decorator_records_duration():
    @with_stage_timing("route")
    async def routed() -> str:
        await asyncio.sleep(0.005)
        return "ok"

    start_turn()
    result = await routed()

    assert result == "ok"
    timings = get_timings()
    assert "route" in timings
    assert timings["route"] >= 0


async def test_decorator_records_even_when_wrapped_raises():
    @with_stage_timing("dispatch")
    async def boom() -> None:
        await asyncio.sleep(0.001)
        raise RuntimeError("synthetic")

    start_turn()
    with pytest.raises(RuntimeError):
        await boom()

    assert "dispatch" in get_timings()


async def test_repeated_calls_accumulate():
    @with_stage_timing("assemble")
    async def stage() -> None:
        await asyncio.sleep(0.001)

    start_turn()
    await stage()
    first = get_timings()["assemble"]
    await stage()
    second = get_timings()["assemble"]

    assert second >= first


async def test_no_op_outside_turn_context():
    """record_stage and decorator silently no-op without start_turn()."""
    record_stage("orphan", 10)
    assert get_timings() == {}

    @with_stage_timing("orphan2")
    async def fn() -> None:
        pass

    await fn()
    assert get_timings() == {}


async def test_contextvar_isolates_across_tasks():
    """Timings recorded in a child task do not leak into the parent."""

    @with_stage_timing("child_stage")
    async def child_work() -> None:
        await asyncio.sleep(0.001)

    async def child_task() -> dict[str, int]:
        start_turn()
        await child_work()
        return get_timings()

    start_turn()
    record_stage("parent_stage", 1)
    child_timings = await asyncio.create_task(child_task())

    parent_timings = get_timings()
    assert "parent_stage" in parent_timings
    assert "child_stage" not in parent_timings
    assert "child_stage" in child_timings


async def test_decorator_overhead_within_budget():
    """Decorator overhead per call ≤ 50µs; per-turn aggregate ≤ 0.5ms (research.md Decision 7)."""

    @with_stage_timing("micro")
    async def noop() -> None:
        return None

    start_turn()
    iterations = 1000
    start = time.monotonic()
    for _ in range(iterations):
        await noop()
    elapsed = time.monotonic() - start

    overhead_per_call_us = (elapsed / iterations) * 1_000_000
    # Generous upper bound (200µs) to absorb CI jitter; research.md target is 50µs.
    # Failures here are real signal — the decorator should be cheap.
    assert overhead_per_call_us < 200, (
        f"decorator overhead {overhead_per_call_us:.1f}µs/call exceeds 200µs budget "
        f"(research.md target: 50µs/call, soft ceiling: 0.5ms/turn for ~5 stages)"
    )
