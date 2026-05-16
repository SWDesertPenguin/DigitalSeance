# SPDX-License-Identifier: AGPL-3.0-or-later

"""Facilitator-sovereignty audit (2026-05-15) — themes B + C closeout.

Unit coverage for the sovereignty fixes that landed without a new
speckit spec (theme A remains deferred to spec 031).

Theme C — ``/tools/facilitator/debug_set_timeouts`` rejects non-
facilitator callers with 403. The handler previously had no role
guard despite the docstring claim; spec 015's ``consecutive_timeouts``
counter is the circuit-breaker primitive, so any session participant
could prime any other participant's counter.

Theme B — ``/tools/debug/export`` scopes per-participant spend +
usage to sponsored-or-self rows, adds a ``session_totals`` aggregate
for the facilitator's cost-control surface, and rejects
``include_sponsored=true`` with a 403 pointing at spec 031's planned
consent flow. The detection-events page redacts ``trigger_snippet``
to the ``CAPCOM_ONLY_REDACTION_SENTINEL`` literal when the source
message was ``capcom_only`` and the caller is not the active CAPCOM.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.participant_api.tools import debug as debug_endpoint
from src.participant_api.tools import detection_events as det_endpoint
from src.participant_api.tools import facilitator as facilitator_endpoint

# ---------------------------------------------------------------------------
# Theme C — debug_set_timeouts role guard
# ---------------------------------------------------------------------------


def _build_debug_set_timeouts_request(execute_result: str = "UPDATE 1") -> SimpleNamespace:
    """Build a stub Request whose pool/log_repo no-op the handler's writes."""
    conn = SimpleNamespace(execute=AsyncMock(return_value=execute_result))
    pool = SimpleNamespace(acquire=lambda: _AcquireCtx(conn))
    log_repo = SimpleNamespace(log_admin_action=AsyncMock(return_value=None))
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(pool=pool, log_repo=log_repo)),
    )


class _AcquireCtx:
    """Async-context-manager shim that yields a stub asyncpg connection."""

    def __init__(self, conn) -> None:
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_debug_set_timeouts_non_facilitator_rejected_with_403() -> None:
    """Theme C — any non-facilitator caller gets 403, not silent acceptance."""
    request = _build_debug_set_timeouts_request()
    caller = SimpleNamespace(
        id="p-attacker",
        session_id="s-1",
        role="participant",
    )
    body = facilitator_endpoint._DebugSetTimeoutsBody(
        participant_id="p-victim",
        consecutive_timeouts=2,
    )
    with pytest.raises(HTTPException) as excinfo:
        await facilitator_endpoint.debug_set_timeouts(request, body, caller)
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "facilitator_only"


@pytest.mark.asyncio
async def test_debug_set_timeouts_facilitator_call_proceeds() -> None:
    """Theme C — facilitator caller still completes the write + audit row."""
    request = _build_debug_set_timeouts_request()
    facilitator = SimpleNamespace(
        id="f-1",
        session_id="s-1",
        role="facilitator",
    )
    body = facilitator_endpoint._DebugSetTimeoutsBody(
        participant_id="p-target",
        consecutive_timeouts=2,
    )
    result = await facilitator_endpoint.debug_set_timeouts(request, body, facilitator)
    assert result["status"] == "updated"
    assert result["participant_id"] == "p-target"
    assert result["consecutive_timeouts"] == 2
    request.app.state.log_repo.log_admin_action.assert_awaited_once()


# ---------------------------------------------------------------------------
# Theme B — debug.export sponsor scoping
# ---------------------------------------------------------------------------


def _make_participant(
    pid: str,
    *,
    invited_by: str | None = None,
    display_name: str | None = None,
    budget_hourly: float | None = None,
    budget_daily: float | None = None,
) -> SimpleNamespace:
    """Build a participant stub with the fields ``_scoped_for_spend`` reads."""
    return SimpleNamespace(
        id=pid,
        display_name=display_name or pid,
        invited_by=invited_by,
        budget_hourly=budget_hourly,
        budget_daily=budget_daily,
    )


def test_debug_export_sponsor_sees_only_sponsored_ai_spend() -> None:
    """Theme B — sponsor's scope omits another sponsor's AI rows.

    Two human sponsors each invite one AI. The default
    ``_scoped_for_spend`` filter from the caller's perspective MUST
    return only their own row + the AI they invited; the other
    sponsor and that sponsor's AI MUST NOT appear.
    """
    sponsor_a = _make_participant("h-a")
    ai_a = _make_participant("ai-a", invited_by="h-a")
    sponsor_b = _make_participant("h-b")
    ai_b = _make_participant("ai-b", invited_by="h-b")
    all_participants = [sponsor_a, ai_a, sponsor_b, ai_b]

    scoped = debug_endpoint._scoped_for_spend(all_participants, "h-a")
    ids = {p.id for p in scoped}

    assert ids == {"h-a", "ai-a"}
    assert "ai-b" not in ids
    assert "h-b" not in ids


def test_debug_export_facilitator_sees_session_totals_not_per_participant() -> None:
    """Theme B — facilitator's spend list narrows to self + sponsored AIs.

    A facilitator who did not sponsor every AI in the session sees
    only their own participant row in the per-participant ``spend``
    array. The cross-participant aggregate (``session_totals``) is
    still computed off the full participants list.
    """
    facilitator = _make_participant("f-1")
    ai_facilitator_sponsored = _make_participant("ai-f", invited_by="f-1")
    ai_other = _make_participant("ai-other", invited_by="h-other")
    other_human = _make_participant("h-other")
    all_participants = [facilitator, ai_facilitator_sponsored, ai_other, other_human]

    scoped = debug_endpoint._scoped_for_spend(all_participants, "f-1")
    scoped_ids = {p.id for p in scoped}

    assert scoped_ids == {"f-1", "ai-f"}
    assert "ai-other" not in scoped_ids
    assert "h-other" not in scoped_ids


@pytest.mark.asyncio
async def test_debug_export_include_sponsored_returns_403_until_spec_031() -> None:
    """Theme B — include_sponsored=true returns 403 pointing at spec 031."""
    facilitator = SimpleNamespace(id="f-1", session_id="s-1", role="facilitator")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(HTTPException) as excinfo:
        await debug_endpoint.export_session(
            request,
            "s-1",
            facilitator,
            include_sponsored=True,
        )
    assert excinfo.value.status_code == 403
    detail = excinfo.value.detail
    assert isinstance(detail, dict)
    assert detail["error"] == "sponsor_consent_required"
    assert "spec 031" in detail["message"]


def test_debug_export_reject_helper_accepts_false() -> None:
    """The 403 helper is a no-op when include_sponsored is not requested."""
    # Should not raise.
    debug_endpoint._reject_unwired_include_sponsored(False)


def _build_capturing_pool(captured: dict, row: dict):
    """Build a stub pool that records the SQL + params handed to fetchrow."""

    async def fake_fetchrow(sql: str, *params):
        captured["sql"] = sql
        captured["params"] = params
        return row

    conn = SimpleNamespace(fetchrow=fake_fetchrow)
    return SimpleNamespace(acquire=lambda: _AcquireCtx(conn))


@pytest.mark.asyncio
async def test_debug_export_session_totals_uses_full_participant_list() -> None:
    """``_fetch_session_totals`` queries ``usage_log`` for every participant id.

    The aggregate is unconditional — it sums cost + tokens across
    every participant in the session, even those outside the caller's
    sponsorship scope, so the facilitator retains cost-control
    visibility without a per-participant breakdown.
    """
    captured: dict = {}
    pool = _build_capturing_pool(
        captured,
        {"total_cost": 12.5, "total_input": 1000, "total_output": 500},
    )
    all_participants = [_make_participant(f"p-{i}") for i in (1, 2, 3)]
    totals = await debug_endpoint._fetch_session_totals(pool, all_participants)

    assert totals == {
        "total_cost_usd": 12.5,
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
    }
    assert "SUM(cost_usd)" in captured["sql"]
    assert "SUM(input_tokens)" in captured["sql"]
    assert "SUM(output_tokens)" in captured["sql"]
    assert set(captured["params"][0]) == {"p-1", "p-2", "p-3"}


@pytest.mark.asyncio
async def test_debug_export_session_totals_empty_session_is_zero() -> None:
    """An empty participant list short-circuits to zeroed totals."""
    pool = SimpleNamespace(acquire=lambda: _AcquireCtx(None))
    totals = await debug_endpoint._fetch_session_totals(pool, [])
    assert totals == {
        "total_cost_usd": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }


# ---------------------------------------------------------------------------
# Theme B — detection-events trigger_snippet redaction
# ---------------------------------------------------------------------------


def _detection_row(
    *,
    turn_number: int = 7,
    participant_id: str = "ai-1",
    trigger_snippet: str | None = "raw private body",
) -> dict:
    """Build a detection_events row in the shape the page returns."""
    return {
        "id": 42,
        "event_class": "ai_question_opened",
        "participant_id": participant_id,
        "trigger_snippet": trigger_snippet,
        "detector_score": 0.9,
        "turn_number": turn_number,
        "timestamp": None,
        "disposition": "pending",
        "last_disposition_change_at": None,
    }


def test_detection_event_trigger_snippet_redacted_for_non_capcom_on_capcom_only_message() -> None:
    """Theme B — facilitator who is NOT the CAPCOM sees the sentinel.

    When the underlying message is ``visibility='capcom_only'``, the
    trigger snippet (which may carry a slice of the message body) is
    replaced with the spec-031-referenced literal sentinel so the
    facilitator cannot read the private content via the detection-
    event surface.
    """
    row = _detection_row()
    visibility_map = {(row["turn_number"], row["participant_id"]): "capcom_only"}
    out = det_endpoint._decorate_event(
        row,
        visibility_map=visibility_map,
        capcom_id="capcom-ai",
        caller_id="f-1",  # facilitator, but NOT the CAPCOM
    )
    assert out["trigger_snippet"] == det_endpoint.CAPCOM_ONLY_REDACTION_SENTINEL
    assert out["trigger_snippet"] == "[redacted: capcom_only message]"


def test_detection_event_trigger_snippet_preserved_for_capcom_caller() -> None:
    """The CAPCOM still sees the snippet on capcom_only-source messages."""
    row = _detection_row()
    visibility_map = {(row["turn_number"], row["participant_id"]): "capcom_only"}
    out = det_endpoint._decorate_event(
        row,
        visibility_map=visibility_map,
        capcom_id="capcom-ai",
        caller_id="capcom-ai",
    )
    assert out["trigger_snippet"] == "raw private body"


def test_detection_event_trigger_snippet_preserved_for_public_message() -> None:
    """``visibility='public'`` events emit the snippet unredacted."""
    row = _detection_row()
    visibility_map = {(row["turn_number"], row["participant_id"]): "public"}
    out = det_endpoint._decorate_event(
        row,
        visibility_map=visibility_map,
        capcom_id="capcom-ai",
        caller_id="f-1",
    )
    assert out["trigger_snippet"] == "raw private body"


def test_detection_event_no_visibility_map_leaves_snippet_unchanged() -> None:
    """Backward compatibility — old call sites that don't thread the map.

    The existing test surface in ``test_022_detection_events_endpoint.py``
    calls ``_decorate_event(row)`` with no extra args; that path must
    keep producing the previous wire shape.
    """
    row = _detection_row()
    out = det_endpoint._decorate_event(row)
    assert out["trigger_snippet"] == "raw private body"
