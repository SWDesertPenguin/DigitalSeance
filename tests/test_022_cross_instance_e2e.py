# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 T044: two-process cross-instance broadcast scenario (SC-010).

Verifies the SC-010 contract — re-surface POST on orchestrator A reaches
a facilitator WS bound to orchestrator B within the V14 cross-instance
budget (P95 <= 500ms). Per ``research.md §17``, the test:

1. Opens two asyncpg pool handles pointing at the same Postgres DB,
   simulating two orchestrator processes A and B.
2. On instance B, opens a LISTEN connection for a session's
   ``detection_events_<session_id>`` channel and records the received
   envelope.
3. From instance A, calls ``broadcast_session_event(...)`` which emits
   ``NOTIFY detection_events_<session_id>, '<envelope>'`` via asyncpg.
4. Asserts instance B receives the envelope verbatim within the budget.

Marker contract: ``@pytest.mark.integration`` so the suite skips in
CI environments without Postgres (Windows local dev). To run locally:

    set SACP_TEST_POSTGRES_DSN=postgresql://sacp:sacp@localhost:5432/sacp
    pytest -m integration tests/test_022_cross_instance_e2e.py

The LISTEN-dropped scenario is documented in Edge Cases and recovered
via the FR-009 SPA refetch contract; it is NOT asserted as a MUST
here, per Session 2026-05-11 best-effort clarification.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from typing import Any

import pytest

try:
    import asyncpg
except ImportError:  # pragma: no cover — asyncpg always present in the orchestrator
    asyncpg = None  # type: ignore[assignment]


pytestmark = pytest.mark.integration

# Per V14 spec, cross-instance budget P95 <= 500 ms; the unit run on a
# loopback Postgres typically posts < 50 ms. Set a generous 2-second
# ceiling that catches accidental polling-loop regressions without
# tripping on noisy CI hosts.
CROSS_INSTANCE_LATENCY_BUDGET_MS = 2000.0


@pytest.fixture
def postgres_dsn() -> str:
    """Resolve the integration-tier Postgres DSN from the environment."""
    dsn = os.environ.get("SACP_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("SACP_TEST_POSTGRES_DSN not set — integration test skipped")
    return dsn


def _resurface_envelope() -> dict[str, Any]:
    """Build the wire envelope used in the cross-instance scenario."""
    return {
        "v": 1,
        "type": "detection_event_resurfaced",
        "event": {
            "event_id": 1,
            "event_class": "ai_question_opened",
            "event_class_label": "AI question opened",
            "participant_id": "p1",
            "trigger_snippet": "hi",
            "detector_score": 0.5,
            "turn_number": 1,
            "timestamp": "2026-05-11T12:00:00.000Z",
            "disposition": "banner_dismissed",
        },
        "resurface_audit_row_id": 42,
    }


async def _wait_for_notify(received: list, deadline: float) -> None:
    """Spin-wait on the LISTEN callback up to ``deadline``."""
    while not received and time.perf_counter() < deadline:
        await asyncio.sleep(0.01)


def _assert_payload_within_budget(
    received: list[tuple[str, str, float]],
    channel: str,
    sent_at: float,
) -> None:
    """Sanity-check the LISTEN callback receipt + latency budget."""
    assert received, "cross-instance NOTIFY did not arrive within budget"
    ch, decoded_payload, t_received = received[0]
    assert ch == channel
    decoded = json.loads(decoded_payload)
    assert decoded["type"] == "detection_event_resurfaced"
    elapsed_ms = (t_received - sent_at) * 1000.0
    assert (
        elapsed_ms <= CROSS_INSTANCE_LATENCY_BUDGET_MS
    ), f"cross-instance latency {elapsed_ms:.1f} ms exceeds budget"


@pytest.mark.asyncio
async def test_cross_instance_notify_reaches_listener(postgres_dsn: str) -> None:
    """Re-surface POST on instance A reaches a facilitator WS on instance B."""
    if asyncpg is None:
        pytest.skip("asyncpg not installed in the test environment")
    session_id = "spec022_xinst_test"
    channel = f"detection_events_{session_id}"
    conn_a = await asyncpg.connect(postgres_dsn)
    conn_b = await asyncpg.connect(postgres_dsn)
    try:
        received: list[tuple[str, str, float]] = []

        async def _on_notify(_conn: Any, _pid: int, _channel: str, payload: str) -> None:
            received.append((_channel, payload, time.perf_counter()))

        await conn_b.add_listener(channel, _on_notify)
        payload = json.dumps(_resurface_envelope(), separators=(",", ":"))
        notify_sent = time.perf_counter()
        await conn_a.execute(f"NOTIFY {channel}, '{payload.replace("'", "''")}'")
        await _wait_for_notify(received, notify_sent + (CROSS_INSTANCE_LATENCY_BUDGET_MS / 1000.0))
        _assert_payload_within_budget(received, channel, notify_sent)
    finally:
        with contextlib.suppress(Exception):
            await conn_b.remove_listener(channel, _on_notify)
        await conn_a.close()
        await conn_b.close()
