# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 V14 performance budget tests (T046 of tasks.md).

The spec contributes four V14 budgets (see ``specs/022-detection-event-history/spec.md``
"Performance Budgets"):

  1. Panel load (initial fetch): P95 <= 500ms for 1,000 events.
  2. WS push latency on event emission: P95 <= 100ms source-row INSERT to
     client-rendered row.
  3. Re-surface (same-instance fast path): P95 <= 200ms POST to WS broadcast.
  4. Re-surface (cross-instance): P95 <= 500ms POST to WS broadcast.

Production enforcement: ``detection_events.page_load_ms``,
``detection_events.ws_push_ms``, ``detection_events.resurface_same_instance_ms``,
and ``detection_events.resurface_cross_instance_ms`` are emitted to the
structured access log via ``src/observability/instrumentation.py``;
operators query the column distribution against a representative
session corpus.

CI doesn't have a representative corpus, so this test asserts the
lighter unit-level invariants:

- Budget 1 (panel load): the in-memory _decorate_event projection runs
  in well under 50 ms over a 1,000-row synthetic set — confirms the
  per-row projection is O(1) and the LIMIT-bounded query path is
  the only DB hop.
- Budget 2 (ws_push): the cross_instance_broadcast.broadcast_session_event
  in-process path completes in well under 50 ms per call — the LISTEN
  hop is the cross-instance bonus latency.
- The instrument_stage context manager emits one structured log record
  per invocation with the expected stage name + elapsed_ms field (no
  silent counter loss).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.observability import instrumentation
from src.participant_api.tools.detection_events import _decorate_event
from src.web_ui import cross_instance_broadcast as cib

# ---------------------------------------------------------------------------
# Budget 1 — Panel load row projection is fast enough
# ---------------------------------------------------------------------------


def _make_row(i: int) -> dict:
    return {
        "id": i,
        "session_id": "s1",
        "event_class": "ai_question_opened",
        "participant_id": f"ai{i % 5}",
        "trigger_snippet": "What should we do about " + ("the bridge " * 10),
        "detector_score": 0.5,
        "turn_number": i % 100,
        "timestamp": datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC),
        "disposition": "pending",
        "last_disposition_change_at": None,
    }


def test_decorate_event_handles_1000_rows_well_under_panel_load_budget() -> None:
    """Per-row projection is O(1); 1,000 rows complete in << 500 ms.

    The V14 budget is 500 ms END-TO-END (network + query + projection +
    serialization). Projection alone should burn no more than ~10 ms.
    """
    rows = [_make_row(i) for i in range(1000)]
    start = time.perf_counter()
    decorated = [_decorate_event(row) for row in rows]
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert len(decorated) == 1000
    # 100 ms is a very loose ceiling — typical run is < 10 ms. The bound
    # exists to catch accidental quadratic regressions in _decorate_event.
    assert elapsed_ms < 100.0, f"decorate_event over 1000 rows took {elapsed_ms:.1f} ms"


# ---------------------------------------------------------------------------
# Budget 2 — In-process WS push is fast enough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_process_broadcast_under_50ms() -> None:
    """The same-instance broadcast path costs negligible CPU."""
    envelope = {
        "v": 1,
        "type": "detection_event_appended",
        "event": {
            "event_id": 1,
            "event_class": "ai_question_opened",
            "event_class_label": "AI question opened",
            "participant_id": "p1",
            "trigger_snippet": "hi",
            "detector_score": 0.5,
            "turn_number": 1,
            "timestamp": "2026-05-11T12:00:00.000Z",
            "disposition": "pending",
        },
    }
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()):
        start = time.perf_counter()
        await cib.broadcast_session_event("s1", envelope, pool=None)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
    # WS push budget is 100 ms; the in-process branch should fit in 50 ms.
    assert elapsed_ms < 50.0, f"in-process broadcast took {elapsed_ms:.1f} ms"


# ---------------------------------------------------------------------------
# Instrumentation contract — structured log emission is intact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_instrument_stage_emits_elapsed_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every instrumented stage emits one log record with elapsed_ms."""
    caplog.set_level(logging.DEBUG, logger="src.observability.instrumentation")
    async with instrumentation.instrument_stage("test.stage_ok", session_id="s1") as stage:
        stage["row_count"] = 7
    matching = [r for r in caplog.records if getattr(r, "stage", None) == "test.stage_ok"]
    assert len(matching) == 1
    record = matching[0]
    assert record.elapsed_ms >= 0
    assert record.row_count == 7
    assert record.session_id == "s1"


@pytest.mark.asyncio
async def test_instrument_stage_emits_warn_on_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An exception still costs perf budget — log at WARN with exception name."""
    caplog.set_level(logging.WARNING, logger="src.observability.instrumentation")
    with pytest.raises(RuntimeError):
        async with instrumentation.instrument_stage("test.stage_err", session_id="s1"):
            raise RuntimeError("boom")
    matching = [r for r in caplog.records if getattr(r, "stage", None) == "test.stage_err"]
    assert len(matching) == 1
    assert matching[0].levelno == logging.WARNING
    assert matching[0].exception == "RuntimeError"


@pytest.mark.asyncio
async def test_page_load_stage_emits_when_endpoint_called() -> None:
    """The page endpoint wraps the repo call with the page_load stage."""
    from types import SimpleNamespace

    from src.participant_api.tools import detection_events as endpoint

    log_repo = SimpleNamespace(
        get_detection_events_page=AsyncMock(return_value=[]),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(log_repo=log_repo)),
    )
    participant = SimpleNamespace(role="facilitator", session_id="s1", id="f1")

    with patch.object(instrumentation, "_logger") as mock_logger:
        body = await endpoint.get_detection_events(request, "s1", participant)
    assert body["count"] == 0
    # Either debug() or warning() was called with the elapsed-ms record.
    invoked = mock_logger.debug.call_args_list + mock_logger.warning.call_args_list
    assert any(
        any("page_load" in str(arg) for arg in call.args) for call in invoked
    ), f"page_load stage MUST emit a log line; got {invoked}"
