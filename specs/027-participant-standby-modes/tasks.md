# Tasks: AI Participant Standby Modes

**Spec**: `specs/027-participant-standby-modes/spec.md`
**Plan**: `specs/027-participant-standby-modes/plan.md`
**Status**: All tasks completed 2026-05-12 in the full-pass clarify + plan + tasks + implement session.

Tasks group by user story priority (P1 / P2 / P3) and by implementation phase (per `plan.md`). Each task cites the implementation file or test file that satisfies it.

## Phase 1 — Schema + status enum + participant model (P1 foundation)

- [X] **T001** — Author migration `alembic/versions/021_participant_standby_modes.py`: add `participants.wait_mode` (TEXT CHECK enum default `wait_for_human`), `participants.standby_cycle_count` (INTEGER default 0), `participants.wait_mode_metadata` (JSONB default `{}`); add `routing_log.standby_eval_ms`, `routing_log.pivot_inject_ms`, `routing_log.standby_transition_ms`; extend `participants.status` CHECK to permit `standby`; create partial index `idx_participants_session_standby`. Forward-only per spec 001 §FR-017.
- [X] **T002** — Mirror the three new `participants` columns in `tests/conftest.py:_PARTICIPANTS_TABLE_DDL` per `feedback_test_schema_mirror`. JSONB mirrors as TEXT with `'{}'` default for the test substrate.
- [X] **T003** — Extend `src/models/participant.py:Participant` with three new fields (`wait_mode`, `standby_cycle_count`, `wait_mode_metadata`). The `from_record` splat continues to work.
- [X] **T004** — Extend `src/repositories/participant_repo.py` row-to-Participant deserialization to parse `wait_mode_metadata` JSONB into a `dict[str, Any]`. Add `update_wait_mode(participant_id, new_mode)` method.
- [X] **T005** — Add four V16 validators to `src/config/validators.py`: `validate_standby_default_wait_mode`, `validate_standby_filler_detection_turns`, `validate_standby_pivot_timeout_seconds`, `validate_standby_pivot_rate_cap_per_session`. Register all four in the `VALIDATORS` tuple.
- [X] **T006** — Add `tests/test_027_validators.py` covering each validator's positive + negative paths (good values, out-of-range, non-int input, missing value, enum mismatch).
- [X] **T007** — Add four env-var entries to `docs/env-vars.md` (six standard fields each per the V16 deliverable contract).
- [X] **T008** — Add `tests/test_027_architectural.py` asserting: (a) all five new audit-action labels registered in both `audit_labels.py` mirrors, (b) all four new env vars registered in `VALIDATORS` tuple, (c) the migration `021_*` is the alembic head, (d) the `_PARTICIPANTS_TABLE_DDL` in `conftest.py` carries the three new columns.

## Phase 2 — Standby evaluator + WS events (P1 critical path)

- [X] **T009** — Author `src/orchestrator/standby.py`: `StandbyEvaluator` class per `contracts/standby-evaluator.md`. Includes the four detection-signal helpers + the evaluate_tick orchestration. O(1) per participant per tick.
- [X] **T010** — Wire the evaluator into `src/orchestrator/loop.py` BEFORE router.next_speaker. Update the round-robin skip-set per StandbyEvalResult.entered/exited. Persist the audit rows + emit WS events.
- [X] **T011** — Add five new audit-action labels (`standby_entered`, `standby_exited`, `pivot_injected`, `standby_observer_marked`, `wait_mode_changed`) to `src/orchestrator/audit_labels.py` AND `frontend/audit_labels.js` (CI parity gate enforces equality).
- [X] **T012** — Add two new WS event types in `src/web_ui/events.py`: `participant_standby` + `participant_standby_exited`. Broadcast to session subscribers.
- [X] **T013** — Implement the `POST /tools/participant/set_wait_mode` endpoint per `contracts/wait-mode-endpoint.md`. Audit row + WS broadcast on success.
- [X] **T014** — Update the observer-downgrade evaluator in `src/orchestrator/observer_downgrade.py` to SKIP participants already in `standby` status (FR-026 precedence).
- [X] **T015** — Add `tests/test_027_standby_evaluator.py` covering each detection signal independently + the precedence chain (paused > standby, circuit_open > standby, standby > observer-downgrade).
- [X] **T016** — Add `tests/test_027_loop_integration.py` driving multi-tick sessions through the evaluator + skip-set + WS event chain (acceptance scenarios US1.1..US1.6).
- [X] **T017** — Add `tests/test_027_ws_events.py` covering `participant_standby` + `participant_standby_exited` + `participant_update` payload extension.

## Phase 3 — `always`-mode Tier 4 delta + composition (P2)

- [X] **T018** — Author `src/prompts/standby_ack_delta.py` with `STANDBY_ACK_TEXT` constant and `standby_ack_delta(active: bool) -> str` helper. Pre-validate the text through `src/security/output_validator.py` at module import (FR-022).
- [X] **T019** — Wire the delta into `src/prompts/tiers.py:assemble_prompt`: add `standby_ack_delta` keyword arg, append AFTER `conclude_delta` and AFTER `register_delta_text` per fixed-additive-order (Session 2026-05-12 Q5).
- [X] **T020** — Wire the dispatch closure in `src/orchestrator/loop.py` to compute `standby_ack_delta(active=...)` based on whether ANY detection signal would have fired in `wait_for_human` mode for the dispatched `always`-mode participant.
- [X] **T021** — Add `tests/test_027_always_mode_delta.py` covering acceptance scenarios US2.1..US2.5 (delta presence when gated, delta absence when ungated, composition with 021 + 025 deltas, response-not-acknowledging-still-persisted edge case).
- [X] **T022** — Add `tests/test_027_delta_composition.py` covering SC-007 (all three deltas appear in documented order).

## Phase 4 — Auto-pivot + long-term-observer + rate cap (P3)

- [X] **T023** — Implement pivot-evaluation helpers in `src/orchestrator/standby.py`: per-participant cycle counter (FR-027 durable column), pivot trigger check (`cycles >= SACP_STANDBY_FILLER_DETECTION_TURNS AND elapsed >= SACP_STANDBY_PIVOT_TIMEOUT_SECONDS`), per-session rate-cap check.
- [X] **T024** — Implement pivot message INSERT in `src/orchestrator/standby.py`: `speaker_type='system'`, `metadata->>'kind' = 'orchestrator_pivot'`, rate_cap_remaining metadata.
- [X] **T025** — Implement long-term-observer transition: UPDATE `wait_mode_metadata` with `long_term_observer=true` for `wait_for_human`-mode pivot targets. Audit `standby_observer_marked`.
- [X] **T026** — Implement long-term-observer exit: when the gating condition clears for a long-term-observer participant, clear the JSONB flag AND clear standby cleanly back to `active` (FR-021).
- [X] **T027** — Add `tests/test_027_pivot_mechanism.py` covering acceptance scenarios US3.1..US3.5 (pivot fires after N cycles + timeout, rate cap prevents second pivot, long-term-observer transition).
- [X] **T028** — Add `tests/test_027_long_term_observer.py` covering the clean-exit path (gate clears → observer + standby clear, no manual reset).

## Phase 5 — Spec 011 amendments + frontend rendering

- [X] **T029** — Add FRs FR-052..FR-059 to `specs/011-web-ui/spec.md` per the Spec 011 Amendment Coordination section of spec 027. Add the "Phase 3d — Standby UI" subsection under `## Implementation Phases`.
- [X] **T030** — Author `frontend/standby_ui.js` (UMD + Node test pattern). Exports `formatWaitModeBadge`, `formatStandbyPill`, `isLongTermObserver`, `formatLongTermObserverBadge`.
- [X] **T031** — Wire `frontend/standby_ui.js` into `frontend/index.html` as a `<script>` tag ahead of `frontend/app.jsx`. Add SRI attribute via the existing precompute path.
- [X] **T032** — Wire the badge + pill + long-term-observer badge into the participant-card renderer in `frontend/app.jsx`. Consume `participant_standby` + `participant_standby_exited` WS events.
- [X] **T033** — Wire the facilitator `wait_mode` toggle into the participant-card admin overlay in `frontend/app.jsx`. POST to `/tools/participant/set_wait_mode` per `contracts/wait-mode-endpoint.md`.
- [X] **T034** — Wire pivot message rendering: messages with `metadata.kind === 'orchestrator_pivot'` render with banner-style styling distinct from regular system messages.
- [X] **T035** — Add `tests/frontend/test_standby_ui.js` (Node-runnable) covering each pure-logic helper.

## Phase 6 — E2E + closeout

- [X] **T036** — Add `tests/e2e/test_027_standby_e2e.py` skip-gated by `SACP_RUN_E2E=1`. End-to-end through FastAPI + WebSocket: drive a session with a question, observe standby + WS + UI; drive a long absence, observe pivot + long-term-observer; resolve gate, observe clean exit.
- [X] **T037** — Add `tests/test_027_perf_regression.py` (extends spec 003 perf framework) asserting `routing_log.standby_eval_ms` P95 < 1ms over a 100-tick session.
- [X] **T038** — Add `tests/test_027_regression_pre_feature.py` asserting that with `SACP_STANDBY_DEFAULT_WAIT_MODE=always` set session-wide, the pre-feature serialized turn loop behavior is byte-identical (no standby fires).
- [X] **T039** — Run the 6 closeout preflights: traceability, doc-deliverables, audit-label parity, detection-taxonomy parity (no change), migration chain (verify `021_*` chains to `018_*` head), spec-version-bump (1.0.0 → 1.1.0 reflecting the FR-027..FR-029 additions).
- [X] **T040** — Flip spec 027 status to `Implemented 2026-05-12`. Update `CLAUDE.md` via the `update-context` script (per Constitution §14.1 step 8).

## Acceptance gate (final)

- [X] Pytest passes (excluding e2e): `.venv/Scripts/python.exe -m pytest tests/ --ignore=tests/e2e`.
- [X] Ruff passes: `.venv/Scripts/python.exe -m ruff check .`.
- [X] Six closeout preflights green.
- [X] Spec 011 amendments FR-052..FR-059 land in the same PR.
