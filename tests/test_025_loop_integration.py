# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 025 full-flow loop integration scaffold (T090 of tasks.md).

DB-gated end-to-end tests that drive a real session through the full
cap -> conclude -> summarizer -> auto-pause cycle. Skipped when
PostgreSQL is not reachable; populated as the spec 013 regression
pattern (`tests/test_013_regression_phase2.py`) demonstrates.

Each test is a placeholder for a Phase 8 deliverable. The unit-level
helpers tested in:

- `tests/test_025_cap_evaluator.py` — trigger fraction, OR semantics,
  finalize quota, exit-on-extension.
- `tests/test_025_conclude_phase.py` — Tier 4 delta injection,
  cadence floor.
- `tests/test_025_disambiguation.py` — cap-set 409 path.
- `tests/test_025_ws_events.py` — WS payload shapes and
  cap-value-leak guard.
- `tests/test_025_active_seconds.py` — elapsed-time read fallback.
- `tests/test_025_validators.py` — five env-var V16 validators.
- `tests/test_025_regression_no_cap.py` — SC-001 no-cap path
  short-circuit.

...cover the architectural contract. The integration tests below
verify that the CONNECTED helpers hit the DB + WS + summarizer pipeline
correctly when driven through a real session-create + start_loop +
turn-dispatch cycle.

Run pre-commit: `uv run pytest tests/test_025_loop_integration.py -v`
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Phase 8 integration test — DB-gated; populate when test env stands up")
async def test_us1_turn_cap_drives_to_auto_pause() -> None:
    """US1 acceptance #1-#5 + SC-002: drive a 20-turn-cap session to auto-pause.

    Steps:
    - Create session with `length_cap_kind='turns', length_cap_turns=20`.
    - Start loop with 3 active AI participants.
    - Run turns to 16; assert `routing_log.reason='conclude_phase_entered'` row.
    - Assert each subsequent dispatch's assembled prompt contains the
      conclude delta.
    - Run turns 17-19; assert spec 005 summarizer row appears (a new
      `messages` row with `speaker_type='summary'`).
    - Assert `routing_log.reason='auto_pause_on_cap'` row.
    - Assert next `execute_turn` raises `SessionNotActiveError`.
    """


@pytest.mark.skip(reason="Phase 8 integration test — DB-gated")
async def test_us1_no_cap_path_unchanged() -> None:
    """SC-001 architectural contract end-to-end: default `kind='none'` session
    runs identically to pre-feature behavior.

    Steps:
    - Create session with default cap (none).
    - Drive 100 turns.
    - Assert NO `conclude_phase_entered` / `auto_pause_on_cap` rows in
      routing_log.
    - Assert NO `speaker_type='summary'` message attributable to FR-011.
    - Assert session.status remains 'active' throughout.
    """


@pytest.mark.skip(reason="Phase 8 integration test — DB-gated")
async def test_us2_mid_session_cap_set_disambiguation_flow() -> None:
    """US2 acceptance #1-#5: mid-session cap-set + 409 disambiguation re-POST.

    Steps:
    - Create session, run 30 turns.
    - PATCH /tools/facilitator/set_length_cap with `length_cap_turns=20`.
    - Assert HTTP 409 + body includes both `absolute` and `relative`
      option payloads.
    - Re-POST with `interpretation='absolute'`; assert HTTP 200.
    - Assert `routing_log.cap_set` row with `interpretation='absolute'`
      via the admin_audit_log payload.
    - Assert next `execute_turn` enters conclude phase.
    """


@pytest.mark.skip(reason="Phase 8 integration test — DB-gated")
async def test_us3_extension_during_conclude_returns_to_running() -> None:
    """US3 acceptance #1-#4: cap extension exits conclude phase.

    Steps:
    - Drive a session into conclude phase (turn-cap 20, currently at 19).
    - PATCH cap to 30.
    - Assert `routing_log.reason='conclude_phase_exited'` row.
    - Assert next assembly does NOT contain conclude delta.
    - Run turns to 24; assert second `conclude_phase_entered` row.
    """


@pytest.mark.skip(reason="Phase 8 integration test — DB-gated")
async def test_us4_manual_stop_during_conclude_runs_summarizer() -> None:
    """US4 acceptance #1-#3: stop_loop in conclude phase still wraps up.

    Steps:
    - Drive a session into conclude phase.
    - Call POST /tools/session/stop_loop after 2 of 3 AIs have produced
      conclude turns.
    - Assert spec 005 summarizer row appears BEFORE the loop status
      transitions.
    - Assert `routing_log.reason='manual_stop_during_conclude'` row.
    """


@pytest.mark.skip(reason="Phase 8 integration test — DB-gated; multi-client WS test")
async def test_us13_ws_broadcast_to_all_participants() -> None:
    """US13 acceptance #3-#6: `session_concluding` reaches every connected client.

    Steps:
    - Connect facilitator + 2 non-facilitator participants via WebSocket.
    - Drive a session into conclude phase.
    - Assert all three clients receive a `session_concluding` event.
    - Assert the event payload does NOT include `length_cap_*` fields
      (FR-019).
    - Assert non-facilitator `/me` responses also do NOT include cap fields.
    """
