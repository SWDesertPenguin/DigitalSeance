---

description: "Task list for implementing spec 025 (session-length cap with auto-conclude phase)"
---

# Tasks: Session-Length Cap with Auto-Conclude Phase

**Input**: Design documents from `/specs/025-session-length-cap/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — spec defines four Independent Tests + 22 Acceptance Scenarios across US1–US4 (plus 6 scenarios for spec 011 US13 amendment), and plan.md enumerates test files per story. Tests land alongside implementation.

**Organization**: Tasks grouped by user story so each can be implemented and tested independently. Phase 2 covers shared infrastructure (V16 deliverable gate per spec 025 FR-025, schema migration with conftest mirror per memory `feedback_test_schema_mirror`, and the SC-001 regression canary). The spec 011 amendment (US13) lands as the final user-story phase since it consumes the WS event emitters from US1+US2.

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, OR independent functions in the same file with no shared edit point)
- **[Story]**: US1 / US2 / US3 / US4 / US13 (no label for Setup, Foundational, Polish)

## Path Conventions

Single project, paths under repo root. Backend code under [src/](src/); frontend under [frontend/](frontend/); tests under [tests/](tests/) per [plan.md "Source Code"](specs/025-session-length-cap/plan.md).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repo hygiene + new module placeholders. Working tree is on `025-session-length-cap` branch off main.

- [X] T001 Verify on branch `025-session-length-cap` and run `python -m src.run_apps --validate-config-only` to confirm V16 baseline passes before any new validators land
- [X] T002 [P] Create empty module skeletons: [src/orchestrator/length_cap.py](src/orchestrator/length_cap.py), [src/prompts/conclude_delta.py](src/prompts/conclude_delta.py) (each containing only a module docstring referencing spec 025)

---

## Phase 2: Foundational (Blocking Prerequisites — V16 Gate per FR-025)

**Purpose**: V16 env-var deliverables (5 validators + 5 docs sections), schema migration with conftest mirror, shared dataclasses, and the SC-001 regression canary. All five user stories depend on these.

**⚠️ CRITICAL**: No user-story task in Phase 3+ may begin until Phase 2 completes. The V16 gate is non-negotiable per spec FR-025.

### V16 deliverable gate (5 validators + 5 doc sections)

- [X] T003 [P] Add `validate_sacp_length_cap_default_kind` to [src/config/validators.py](src/config/validators.py) per [contracts/env-vars.md §SACP_LENGTH_CAP_DEFAULT_KIND](specs/025-session-length-cap/contracts/env-vars.md): enum in `{none, time, turns, both}`; default `none`; out-of-enum exits at startup
- [X] T004 [P] Add `validate_sacp_length_cap_default_seconds` to [src/config/validators.py](src/config/validators.py): empty OR positive int in `[60, 2_592_000]`; out-of-range exits at startup
- [X] T005 [P] Add `validate_sacp_length_cap_default_turns` to [src/config/validators.py](src/config/validators.py): empty OR positive int in `[1, 10_000]`; out-of-range exits at startup
- [X] T006 [P] Add `validate_sacp_conclude_phase_trigger_fraction` to [src/config/validators.py](src/config/validators.py): float in strict `(0.0, 1.0)`; default `0.80`; 0.0 / 1.0 inclusive or outside range exits at startup
- [X] T007 [P] Add `validate_sacp_conclude_phase_prompt_tier` to [src/config/validators.py](src/config/validators.py): int in `{1, 2, 3, 4}`; default `4`; out-of-set exits at startup
- [X] T008 Append the five new validators to the `VALIDATORS` tuple at the bottom of [src/config/validators.py](src/config/validators.py) (depends on T003-T007)
- [X] T009 [P] Add `### SACP_LENGTH_CAP_DEFAULT_KIND` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields per [contracts/env-vars.md](specs/025-session-length-cap/contracts/env-vars.md)
- [X] T010 [P] Add `### SACP_LENGTH_CAP_DEFAULT_SECONDS` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields
- [X] T011 [P] Add `### SACP_LENGTH_CAP_DEFAULT_TURNS` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields
- [X] T012 [P] Add `### SACP_CONCLUDE_PHASE_TRIGGER_FRACTION` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields
- [X] T013 [P] Add `### SACP_CONCLUDE_PHASE_PROMPT_TIER` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields
- [X] T014 Run `python scripts/check_env_vars.py` from repo root and confirm V16 CI gate green for the five new vars (validators + doc sections in lockstep)
- [X] T015 [P] Validator unit tests in [tests/test_025_validators.py](tests/test_025_validators.py): each of the five validators — valid value passes, out-of-range raises `ConfigValidationError` naming the offending var, empty handled per the var's allowed-empty rule

### Schema migration + conftest mirror (single landing per memory feedback_test_schema_mirror)

- [X] T016 Generate alembic migration `NNNN_session_length_cap.py` in [alembic/versions/](alembic/versions/) per [data-model.md "Schema additions"](specs/025-session-length-cap/data-model.md): five nullable columns on `sessions` (`length_cap_kind` text default `'none'` with CHECK; `length_cap_seconds` bigint with range CHECK; `length_cap_turns` integer with range CHECK; `conclude_phase_started_at` timestamptz; `active_seconds_accumulator` bigint with `>= 0` CHECK) AND mirror the same five column declarations into [tests/conftest.py](tests/conftest.py) raw DDL in the same task
- [X] T017 Extend [src/models/session.py](src/models/session.py) with the five new fields + matching pydantic / dataclass serializer entries per [data-model.md §SessionLengthCap](specs/025-session-length-cap/data-model.md)
- [X] T018 [P] Schema-mirror integrity test in [tests/test_schema_mirror.py](tests/test_schema_mirror.py) (or extend existing): assert raw DDL matches alembic-generated columns for the five new fields (catches the cp/CI drift class memory `feedback_test_schema_mirror` documents) — covered by existing automated `scripts/check_schema_mirror.py` gate; new columns verified in lockstep

### Shared dataclasses + types

- [X] T019 [P] Implement `SessionLengthCap` frozen dataclass in [src/orchestrator/length_cap.py](src/orchestrator/length_cap.py) per [data-model.md §SessionLengthCap](specs/025-session-length-cap/data-model.md): `kind`, `seconds`, `turns`, `conclude_phase_started_at`, `active_seconds_accumulator`
- [X] T020 [P] Add `CapInterpretation` Literal (`'absolute' | 'relative'`) and `CapSetEvent` dataclass in [src/orchestrator/length_cap.py](src/orchestrator/length_cap.py) per [data-model.md §CapInterpretation](specs/025-session-length-cap/data-model.md)
- [X] T021 Extend [src/orchestrator/types.py](src/orchestrator/types.py) `RoutingLogReason` with the five new entries (`cap_set`, `conclude_phase_entered`, `conclude_phase_exited`, `auto_pause_on_cap`, `manual_stop_during_conclude`) per [contracts/routing-log-reasons.md](specs/025-session-length-cap/contracts/routing-log-reasons.md) — added as `LengthCapRoutingReason` Literal alongside new `LoopState` Literal in `types.py`
- [X] T022 Extend the loop FSM state set in [src/orchestrator/loop.py](src/orchestrator/loop.py) (or wherever the existing `LoopState` literal lives — confirm in [src/orchestrator/types.py](src/orchestrator/types.py)) to include `conclude` alongside `running`, `paused`, `stopped` — added as `LoopState` Literal in `types.py`

### SC-001 regression canary

- [X] T023 [P] Regression canary [tests/test_025_regression_no_cap.py](tests/test_025_regression_no_cap.py): assert no spec 025 code path fires when `length_cap_kind='none'` (architectural test per spec.md SC-001 — runs early as a leak detector before US-phase code grows)

**Checkpoint**: V16 gate green; schema migration + conftest mirror landed; shared dataclasses available; SC-001 canary in place. User-story phases unblocked.

---

## Phase 3: User Story 1 — Turn cap → conclude phase → final summarizer → auto-pause (Priority: P1) 🎯 MVP

**Goal**: Facilitator picks a turn-cap preset at session-create; loop runs normally; at trigger fraction the conclude phase fires (Tier 4 delta + cadence suspended); each active AI gets one wrap-up turn; spec 005 summarizer fires once; loop pauses with `auto_pause_on_cap`.

**Independent Test**: Drive a session-create with `length_cap_kind='turns', length_cap_turns=20`. Run AI turns through 16. At turn 17 dispatch, assert assembled prompt contains the conclude delta. Run remaining conclude turns; assert summarizer fires; assert loop is paused with `routing_log.reason='auto_pause_on_cap'`.

### Tests for User Story 1

- [X] T024 [P] [US1] Acceptance scenario 1 (FSM transition + `conclude_phase_entered` row at turn 16) — unit-tested via `evaluate_per_dispatch_cap` in [tests/test_025_cap_evaluator.py](tests/test_025_cap_evaluator.py); loop-integration assertion deferred to Phase 8 integration test (T090)
- [X] T025 [P] [US1] Acceptance scenario 2 (Tier 4 conclude delta in next assembled prompt; participant `custom_prompt` preserved) in [tests/test_025_conclude_phase.py](tests/test_025_conclude_phase.py)
- [ ] T026 [P] [US1] Acceptance scenario 3 (summarizer fires exactly once after last conclude turn) — pending loop integration (T037); unit-level coverage of `run_final_summarizer` wrapper to land alongside loop wiring
- [ ] T027 [P] [US1] Acceptance scenario 4 (`auto_pause_on_cap` row + paused FSM after summarizer) — pending loop integration (T037)
- [X] T028 [P] [US1] Acceptance scenario 5 (spec 004 adaptive cadence suspended during conclude; floor delays returned) in [tests/test_025_conclude_phase.py](tests/test_025_conclude_phase.py)
- [ ] T029 [P] [US1] Skip-and-continue test (conclude-turn provider error after retry cap exhausted: failed AI skipped, summarizer still fires) — pending loop integration (T037)

### Implementation for User Story 1

- [X] T030 [P] [US1] Implement `CONCLUDE_DELTA_TEXT` constant + injection helper in [src/prompts/conclude_delta.py](src/prompts/conclude_delta.py) per [research.md §5](specs/025-session-length-cap/research.md) (two-sentence English, ~45 tokens)
- [X] T031 [US1] Extend [src/prompts/tiers.py](src/prompts/tiers.py) `assemble_prompt` with optional `conclude_delta` parameter per [research.md §4](specs/025-session-length-cap/research.md): additive at Tier 4 after `custom_prompt`; spec 021 register-slider delta (when 021 ships) attaches in the documented slot ahead of conclude delta
- [X] T032 [US1] Implement `evaluate_trigger_fraction(cap, elapsed_turns, elapsed_seconds, trigger_fraction)` plus `is_at_or_past_cap` helpers in [src/orchestrator/length_cap.py](src/orchestrator/length_cap.py); cap-check is O(1) per [plan.md "Performance Goals"](specs/025-session-length-cap/plan.md)
- [X] T033 [US1] Wire per-dispatch cap-check call site into [src/orchestrator/loop.py](src/orchestrator/loop.py): `_evaluate_length_cap` runs at the top of `execute_turn` after the session-active check; SC-001 short-circuit on `length_cap_kind='none'`. V14 stage-timing instrumentation deferred to Phase 8 (T088) since the helper is O(1) with no measurable hot path until DB-gated profiling lands.
- [X] T034 [US1] Wire conclude-phase delta injection through [src/orchestrator/loop.py](src/orchestrator/loop.py) and [src/orchestrator/context.py](src/orchestrator/context.py): `phase` keyword threads from `execute_turn` -> `_execute_routed_turn` -> `_dispatch_with_delay` -> `_dispatch_and_persist` -> `_assemble_and_dispatch` -> `assembler.assemble` -> `_add_system_prompt`, which calls `conclude_delta(active=phase == 'conclude')` and passes the result to `assemble_prompt`
- [X] T035 [US1] Add conclude-phase suspension hook to [src/orchestrator/cadence.py](src/orchestrator/cadence.py) `compute_delay`: new `phase` keyword (default `'running'`); when `phase == 'conclude'`, return preset floor immediately (FR-010)
- [X] T036 [US1] Implement `run_final_summarizer(session_id)` entry point on `SummarizationManager` in [src/orchestrator/summarizer.py](src/orchestrator/summarizer.py): reuses existing spec 005 checkpoint pipeline; called once per conclude-phase entry; respects spec 005 §FR-007 fail-closed (FR-011, FR-012)
- [X] T037 [US1] Wire `running -> conclude -> paused` FSM edges in [src/orchestrator/loop.py](src/orchestrator/loop.py): `_enter_conclude_phase` emits `conclude_phase_entered` at trigger; in-memory `_conclude_started_turn` map tracks the trigger turn; `_maybe_finalize_conclude_phase` runs the final summarizer after every active AI has had its conclude turn (per `should_finalize_conclude_phase` quota), then `update_status('paused')` and emits `auto_pause_on_cap`; subsequent `execute_turn` calls raise `SessionNotActiveError` (caller's standard signal that the loop has paused)
- [X] T038 [US1] Persist `conclude_phase_started_at` and surface helpers on [src/repositories/session_repo.py](src/repositories/session_repo.py): `mark_conclude_phase_started` and `clear_conclude_phase`. `active_seconds_accumulator` writes are wired in US2 (T051/T052) since US1 only consumes turn-cap (the column stays NULL on US1's path).

**Checkpoint**: US1 fully functional and testable independently. MVP increment: a Short-preset session reaches a clean wrap-up under the 20-turn cap.

---

## Phase 4: User Story 2 — Time cap mid-session + cap-set endpoint + disambiguation (Priority: P1)

**Goal**: Facilitator sets a cap mid-session via session-settings (or MCP tool); loop respects it from the moment it commits. When the new value would land below current elapsed, the endpoint returns 409 with both interpretation options; facilitator picks `absolute` or `relative` and re-POSTs with the explicit `interpretation` field.

**Independent Test**: Drive a session running for 90 minutes. PATCH session-settings with `length_cap_kind='time', length_cap_seconds=7200`. Assert `cap_set` row written. Advance clock to 96 minutes; assert conclude phase triggers. Verify pause-resume does not advance `active_seconds_accumulator`.

### Tests for User Story 2

- [ ] T039 [P] [US2] Acceptance scenario 1 (`cap_set` row with old + new values + `actor_id`) in [tests/test_025_active_seconds.py](tests/test_025_active_seconds.py)
- [ ] T040 [P] [US2] Acceptance scenario 2 (time-cap conclude triggers when active_seconds crosses fraction × seconds) in [tests/test_025_active_seconds.py](tests/test_025_active_seconds.py)
- [ ] T041 [P] [US2] Acceptance scenario 3 (cap committed when elapsed already past trigger fraction → conclude triggers immediately on next dispatch) in [tests/test_025_active_seconds.py](tests/test_025_active_seconds.py)
- [ ] T042 [P] [US2] Acceptance scenario 4 (OR semantics: both caps set, either dimension's trigger fires conclude) in [tests/test_025_cap_evaluator.py](tests/test_025_cap_evaluator.py)
- [ ] T043 [P] [US2] Acceptance scenario 5 (10-minute pause → `active_seconds_accumulator` advances by 0 during pause; resumes incrementing on resume) in [tests/test_025_active_seconds.py](tests/test_025_active_seconds.py)
- [ ] T044 [P] [US2] Disambiguation: 409 returned on cap-decrease without `interpretation`; both options present in body per [contracts/cap-set-endpoint.md](specs/025-session-length-cap/contracts/cap-set-endpoint.md) in [tests/test_025_disambiguation.py](tests/test_025_disambiguation.py)
- [ ] T045 [P] [US2] Disambiguation: 200 returned on `interpretation='absolute'` re-POST (immediate conclude triggered); `routing_log.cap_set.interpretation='absolute'` in [tests/test_025_disambiguation.py](tests/test_025_disambiguation.py)
- [ ] T046 [P] [US2] Disambiguation: 200 returned on `interpretation='relative'` re-POST (effective cap = current_elapsed + submitted); `routing_log.cap_set.interpretation='relative'` in [tests/test_025_disambiguation.py](tests/test_025_disambiguation.py)
- [ ] T047 [P] [US2] Disambiguation: 422 returned when `interpretation` field set on a non-decrease request in [tests/test_025_disambiguation.py](tests/test_025_disambiguation.py)
- [ ] T048 [P] [US2] Auth: 403 returned on cap-set by non-facilitator participant per FR-016 in [tests/test_025_disambiguation.py](tests/test_025_disambiguation.py)
- [ ] T049 [P] [US2] MCP tool variant `update_session_length_cap` returns same `options` payload on cap-decrease in [tests/test_025_disambiguation.py](tests/test_025_disambiguation.py)
- [ ] T050 [P] [US2] Validation: each of the eight 422 cases (range violations + cross-column constraint violations) per [contracts/cap-set-endpoint.md "Validation"](specs/025-session-length-cap/contracts/cap-set-endpoint.md) in [tests/test_025_validators.py](tests/test_025_validators.py)

### Implementation for User Story 2

- [ ] T051 [US2] Implement `update_active_seconds(session, now)` in [src/orchestrator/length_cap.py](src/orchestrator/length_cap.py): increments `active_seconds_accumulator` by `now - last_phase_change_at` only when current phase is `running` or `conclude` per [data-model.md §ActiveLoopAccumulator](specs/025-session-length-cap/data-model.md) (depends on T032)
- [ ] T052 [US2] Add `active_seconds_accumulator` update call sites to [src/orchestrator/loop.py](src/orchestrator/loop.py) at every FSM transition (running ↔ paused, running ↔ conclude, conclude → paused/stopped); add startup-recovery walk per [data-model.md §"Restart recovery"](specs/025-session-length-cap/data-model.md)
- [ ] T053 [US2] Implement `detect_decrease_intent(session, submitted)` helper in [src/orchestrator/length_cap.py](src/orchestrator/length_cap.py) per [research.md §7](specs/025-session-length-cap/research.md): returns `CapUpdatePlan` (clean) OR `DisambiguationRequired` (with both interpretation options + consequences)
- [ ] T054 [US2] Extend session-settings endpoint in [src/web_ui/session_controls.py](src/web_ui/session_controls.py) to accept `length_cap_*` fields + optional `interpretation`; calls `detect_decrease_intent`; emits 409 with both options when decrease without `interpretation` per [contracts/cap-set-endpoint.md](specs/025-session-length-cap/contracts/cap-set-endpoint.md)
- [ ] T055 [US2] Add cap-set MCP tool variant `update_session_length_cap` in [src/mcp_server/tools.py](src/mcp_server/tools.py): mirrors HTTP shape; calls same `detect_decrease_intent` helper; returns structured tool error on disambiguation
- [ ] T056 [US2] Add facilitator-only auth guard to cap-set endpoint + MCP tool (mirrors spec 006 §FR-007 pattern); 403 on non-facilitator (FR-016)
- [ ] T057 [US2] Wire `cap_set` row emission into [src/repositories/log_repo.py](src/repositories/log_repo.py) (or wherever `routing_log` writes happen) with `old_cap`, `new_cap`, `interpretation`, `actor_id`, `current_elapsed_at_set` per [contracts/routing-log-reasons.md §cap_set](specs/025-session-length-cap/contracts/routing-log-reasons.md)
- [ ] T058 [US2] Validation rules in cap-set endpoint per FR-020/FR-021/FR-022/FR-026: range checks; cross-column consistency (`kind=time` requires seconds, etc.); `interpretation` only valid on cap-decrease; emit appropriate 422 error codes per [contracts/cap-set-endpoint.md "Validation"](specs/025-session-length-cap/contracts/cap-set-endpoint.md)

**Checkpoint**: US2 functional. Time caps and mid-session updates work end-to-end; the disambiguation flow is testable via curl + MCP. Combined with US1, the spec's primary value is delivered.

---

## Phase 5: User Story 3 — Cap extension during conclude phase (Priority: P2)

**Goal**: Facilitator extends the cap mid-conclude (e.g., 20 → 50 turns at turn 19); loop transitions back to running phase (`conclude_phase_exited`); conclude delta removed from next assembly; spec 004 cadence resumes; conclude phase can re-trigger when the new threshold is crossed.

**Independent Test**: Drive a session into conclude phase. Before final summarizer fires, extend cap (e.g., 20 → 30 turns). Assert `conclude_phase_exited` row. Assert next assembly does NOT contain conclude delta. Run through to turn 24; assert conclude phase triggers a second time.

### Tests for User Story 3

- [ ] T059 [P] [US3] Acceptance scenario 1 (`conclude → running` transition with `conclude_phase_exited` row when extension moves trigger fraction past elapsed) in [tests/test_025_conclude_phase.py](tests/test_025_conclude_phase.py)
- [ ] T060 [P] [US3] Acceptance scenario 2 (next assembly after exit does NOT contain conclude delta) in [tests/test_025_conclude_phase.py](tests/test_025_conclude_phase.py)
- [ ] T061 [P] [US3] Acceptance scenario 3 (spec 004 cadence resumes after exit; non-floor delays return) in [tests/test_025_conclude_phase.py](tests/test_025_conclude_phase.py)
- [ ] T062 [P] [US3] Acceptance scenario 4 (conclude phase re-triggers when new trigger fraction crossed; multiple `conclude_phase_entered` rows per session valid) in [tests/test_025_conclude_phase.py](tests/test_025_conclude_phase.py)

### Implementation for User Story 3

- [ ] T063 [US3] Implement `evaluate_extension_exit(cap, elapsed)` helper in [src/orchestrator/length_cap.py](src/orchestrator/length_cap.py): returns whether the new cap moves the trigger fraction past current elapsed; if so, signal exit to running
- [ ] T064 [US3] Wire `conclude → running` FSM edge into the cap-set commit path in [src/orchestrator/loop.py](src/orchestrator/loop.py): when `evaluate_extension_exit` is true, emit `conclude_phase_exited` row, clear `conclude_phase_started_at`, restore cadence (depends on T035, T053, T057)
- [ ] T065 [US3] Confirm prompt assembler does NOT inject conclude delta when `loop_state == 'running'` after a `conclude → running` exit (test T060 verifies this; impl is the inverse of T034's gate)

**Checkpoint**: US3 functional. Cap-extension UX works as the operator expects; the exit + re-entry cycle is auditable in `routing_log`.

---

## Phase 6: User Story 4 — Manual stop_loop during conclude (Priority: P3)

**Goal**: Facilitator clicks "Stop loop" while conclude phase is running; orchestrator runs the final summarizer on the conclusions produced so far BEFORE transitioning to stopped; preserves the wrap-up-artifact promise even on early manual abort.

**Independent Test**: Drive a session into conclude phase. After 2 of N AIs have produced conclude turns, call `stop_loop`. Assert spec 005 summarizer fires before stopped transition. Assert `manual_stop_during_conclude` row with `conclude_turns_pending_at_stop` accounting.

### Tests for User Story 4

- [ ] T066 [P] [US4] Acceptance scenario 1 (summarizer fires before `stopped` transition when `stop_loop` called during conclude) in [tests/test_025_manual_stop.py](tests/test_025_manual_stop.py)
- [ ] T067 [P] [US4] Acceptance scenario 2 (`manual_stop_during_conclude` row with `actor_id`, `conclude_turns_produced`, `conclude_turns_pending_at_stop` accounting) in [tests/test_025_manual_stop.py](tests/test_025_manual_stop.py)
- [ ] T068 [P] [US4] Acceptance scenario 3 (summarizer failure still allows `stopped` transition per spec 005 §FR-007 fail-closed) in [tests/test_025_manual_stop.py](tests/test_025_manual_stop.py)

### Implementation for User Story 4

- [ ] T069 [US4] Extend `stop_loop` handler in [src/orchestrator/loop.py](src/orchestrator/loop.py) (or session-control endpoints in [src/web_ui/session_controls.py](src/web_ui/session_controls.py)): when current phase is `conclude`, run `final_summarizer_trigger` BEFORE transitioning to `stopped` (depends on T036, T037)
- [ ] T070 [US4] Wire `manual_stop_during_conclude` row emission with `conclude_turns_pending_at_stop` accounting per [contracts/routing-log-reasons.md §manual_stop_during_conclude](specs/025-session-length-cap/contracts/routing-log-reasons.md)

**Checkpoint**: US4 functional. Manual stop during conclude phase preserves the wrap-up-artifact promise.

---

## Phase 7: User Story 13 — Spec 011 length-cap UI surface (Priority: P2)

**Goal**: Wire the four UI surfaces from the spec 011 amendment (FR-021..FR-024): cap-config control set in session-create modal, cap-config control set in facilitator session-settings panel, conclude-phase banner driven by WS events, cap-decrease disambiguation modal driven by 409. Backend WS event emitters land here too.

**Independent Test**: Playwright e2e per spec 011 SC-007 (Phase 3): facilitator sets a cap at session-create AND mid-session; conclude banner renders for all connected participants on `session_concluding`; disambiguation modal appears on cap-decrease and routes to a successful 200 commit on either choice.

### Tests for User Story 13

- [ ] T071 [P] [US13] WS broadcast: `session_concluding` payload shape per [contracts/ws-events.md §session_concluding](specs/025-session-length-cap/contracts/ws-events.md) (`trigger_reason`, `trigger_value`, `remaining`, `trigger_fraction`, `at`) in [tests/test_025_ws_events.py](tests/test_025_ws_events.py)
- [ ] T072 [P] [US13] WS broadcast: `session_concluded` payload shape with `pause_reason`, `summarizer_outcome` per [contracts/ws-events.md §session_concluded](specs/025-session-length-cap/contracts/ws-events.md)
- [ ] T073 [P] [US13] Cap-value-leak test: assert `session_concluding` payload does NOT include `length_cap_seconds` or `length_cap_turns`; `/me` for non-facilitator participants does NOT include `length_cap_*` fields (FR-019 enforcement) in [tests/test_025_ws_events.py](tests/test_025_ws_events.py)
- [ ] T074 [P] [US13] Multi-client broadcast: facilitator + non-facilitator both receive `session_concluding` and `session_concluded` events in [tests/test_025_ws_events.py](tests/test_025_ws_events.py)
- [ ] T075 [P] [US13] Playwright e2e: session-create modal Short preset commits `length_cap_kind='both'`, `length_cap_seconds=1800`, `length_cap_turns=20` in [tests/frontend/test_025_cap_create.spec.py](tests/frontend/test_025_cap_create.spec.py)
- [ ] T076 [P] [US13] Playwright e2e: facilitator session-settings panel cap update mid-session lands a 200 + `cap_set` row in [tests/frontend/test_025_cap_settings.spec.py](tests/frontend/test_025_cap_settings.spec.py)
- [ ] T077 [P] [US13] Playwright e2e: conclude banner renders on `session_concluding` for both facilitator and non-facilitator clients; clears on `session_concluded` in [tests/frontend/test_025_conclude_banner.spec.py](tests/frontend/test_025_conclude_banner.spec.py)
- [ ] T078 [P] [US13] Playwright e2e: cap-decrease disambiguation modal — both interpretation options selectable; absolute path triggers immediate conclude phase; relative path interprets as additive turns/seconds in [tests/frontend/test_025_disambiguation_modal.spec.py](tests/frontend/test_025_disambiguation_modal.spec.py)

### Implementation for User Story 13

- [ ] T079 [US13] Implement `session_concluding` WS event emitter in [src/web_ui/events.py](src/web_ui/events.py); broadcast on `running → conclude` FSM transition per [contracts/ws-events.md §session_concluding](specs/025-session-length-cap/contracts/ws-events.md) (depends on T037)
- [ ] T080 [US13] Implement `session_concluded` WS event emitter in [src/web_ui/events.py](src/web_ui/events.py); broadcast on `conclude → paused` and `conclude → stopped` transitions; payload includes `summarizer_outcome` (depends on T037, T070)
- [ ] T081 [US13] Build cap-config control component (UMD module pattern per memory `frontend_polish_module_pattern`): preset selector (Short/Medium/Long/Custom) + custom-value inputs in [frontend/cap_config.js](frontend/cap_config.js); Node-runnable unit tests under [tests/frontend/test_025_cap_config_unit.py](tests/frontend/test_025_cap_config_unit.py)
- [ ] T082 [US13] Wire cap-config control into the session-create modal in [frontend/app.jsx](frontend/app.jsx) per spec 011 FR-021
- [ ] T083 [US13] Wire cap-config control + current-elapsed display into the facilitator session-settings panel in [frontend/app.jsx](frontend/app.jsx) per spec 011 FR-022; gate on FR-009 facilitator role check
- [ ] T084 [US13] Build conclude-phase banner component in [frontend/conclude_banner.js](frontend/conclude_banner.js) per spec 011 FR-023: consumes `remaining.turns` / `remaining.seconds` from `session_concluding`; renders "Session is concluding — N turns left" / "N minutes left"; clears on `session_concluded` OR `loop_state_changed → running`
- [ ] T085 [US13] Wire conclude-phase banner into [frontend/app.jsx](frontend/app.jsx) at the top of the participant view; ensures cap values themselves never appear in DOM (spec 025 FR-019 + spec 011 FR-023)
- [ ] T086 [US13] Build disambiguation modal component in [frontend/cap_disambiguation.js](frontend/cap_disambiguation.js) per spec 011 FR-024: triggered by 409 `cap_decrease_requires_interpretation`; renders both options + consequence text; routes to re-POST with explicit `interpretation`; no auto-pick default
- [ ] T087 [US13] Wire disambiguation modal into the cap-set client helper in [frontend/app.jsx](frontend/app.jsx); intercept 409 response from session-settings endpoint and route to the modal

**Checkpoint**: US13 functional. End-to-end UX works: facilitator sets caps, participants see the banner, the disambiguation modal handles cap-decrease intent. Spec 011 SC-007 e2e passes.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: V14 perf instrumentation, integration test for the full flow, quickstart validation, and cross-spec audit.

- [ ] T088 [P] V14 perf instrumentation: confirm cap-check stage timing lands in `routing_log` per-stage timings (FR-005, plan.md "Performance Goals"); add a benchmark assertion that cap-check P95 stays below the existing per-stage baseline in [tests/test_025_perf.py](tests/test_025_perf.py)
- [ ] T089 [P] V14 perf instrumentation: confirm conclude-phase transition timing lands in `routing_log`; assert P95 < 2s at 5 active participants (plan.md "Performance Goals")
- [ ] T090 [P] Full-flow integration test in [tests/test_025_loop_integration.py](tests/test_025_loop_integration.py): cap → conclude → final summarizer → auto-pause across 3-AI scenario; mirrors quickstart.md "Watch the conclude phase fire" walk-through
- [ ] T091 [P] Cross-spec FR audit: confirm spec 003 §FR-021 (FSM lifecycle) callers updated for the new conclude state; confirm spec 003 §FR-030 (per-stage timing) call sites cover cap-check; confirm spec 003 §FR-031 (compound retry cap) applies to conclude turns per FR-011
- [ ] T092 [P] Spec 011 amendment alignment: confirm spec 011 FR-021..FR-024 wording matches the implemented UI surface; if implementation drift required adjustment, update [specs/011-web-ui/spec.md](specs/011-web-ui/spec.md) under a follow-up Clarifications session entry
- [ ] T093 Run quickstart.md walk-through end-to-end against a local Dockge stack: set the five env vars, restart, create a session with Short preset, drive turns to conclude, observe summarizer + auto-pause; document any drift between quickstart text and observed behavior in a follow-up Clarifications session entry on [specs/025-session-length-cap/spec.md](specs/025-session-length-cap/spec.md)
- [ ] T094 [P] ruff + standards-lint pass on all new files: [src/orchestrator/length_cap.py](src/orchestrator/length_cap.py), [src/prompts/conclude_delta.py](src/prompts/conclude_delta.py), modified loop/cadence/summarizer files; confirm 25/5 limits per Constitution §6.10

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — branch is already created from prior commit
- **Foundational (Phase 2)**: Depends on Setup — V16 gate (T003-T015) + schema (T016-T018) + dataclasses (T019-T022) + canary (T023). BLOCKS all user stories
- **User Story 1 (Phase 3, P1)**: Depends on Phase 2 — primary value increment (cap → conclude → summarizer → pause)
- **User Story 2 (Phase 4, P1)**: Depends on Phase 2 + builds on US1's FSM helpers (T032). Cap-set + disambiguation + active_seconds. **Note**: technically can proceed in parallel with US1 if T032 is split; sequential order in this list reflects MVP first
- **User Story 3 (Phase 5, P2)**: Depends on US1 (conclude FSM) + US2 (cap-set endpoint)
- **User Story 4 (Phase 6, P3)**: Depends on US1 (conclude FSM + summarizer trigger)
- **User Story 13 (Phase 7, P2)**: Depends on US1 + US2 (WS event emitters need conclude FSM transitions + cap-set 409 path)
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### User Story Dependencies (recap)

- **US1**: Phase 2 → US1 (no story dependencies)
- **US2**: Phase 2 → US2; reuses T032 helpers from US1
- **US3**: US1 + US2 → US3
- **US4**: US1 → US4
- **US13**: US1 + US2 → US13 (frontend can start once WS event emitters land in T079, T080)

### Within Each User Story

- Tests (which are included for this spec) MUST be written and FAIL before implementation per the test-first convention from Phase 2's SC-001 canary
- Models / dataclasses before services; services before endpoints; endpoints before routing_log emissions
- Frontend tasks within US13 can run in parallel once backend WS emitters land (T079, T080 unblock T082-T087)

### Parallel Opportunities

- All Phase 2 [P] validator + doc tasks (T003-T013, except T008 and T014 which aggregate) can run in parallel
- All Phase 2 [P] dataclass tasks (T019, T020, T023) can run in parallel
- All [P] test tasks within a user story can run in parallel
- Implementation tasks across user stories (US1 + US2) can run in parallel after Phase 2 if team capacity allows
- US13 frontend module work (T081, T084, T086) can run in parallel — different UMD module files
- All Phase 8 [P] polish tasks can run in parallel

---

## Parallel Example: Phase 2 V16 deliverable gate

```bash
# Five validator additions in src/config/validators.py (different functions, no shared edit point):
Task: "T003 [P] validate_sacp_length_cap_default_kind"
Task: "T004 [P] validate_sacp_length_cap_default_seconds"
Task: "T005 [P] validate_sacp_length_cap_default_turns"
Task: "T006 [P] validate_sacp_conclude_phase_trigger_fraction"
Task: "T007 [P] validate_sacp_conclude_phase_prompt_tier"

# Five docs/env-vars.md sections in parallel:
Task: "T009 [P] SACP_LENGTH_CAP_DEFAULT_KIND section"
Task: "T010 [P] SACP_LENGTH_CAP_DEFAULT_SECONDS section"
Task: "T011 [P] SACP_LENGTH_CAP_DEFAULT_TURNS section"
Task: "T012 [P] SACP_CONCLUDE_PHASE_TRIGGER_FRACTION section"
Task: "T013 [P] SACP_CONCLUDE_PHASE_PROMPT_TIER section"

# Then T008 (append to VALIDATORS tuple) + T014 (CI gate verification) run sequentially.
```

---

## Parallel Example: User Story 1 tests

```bash
# All US1 acceptance tests run in parallel (different test functions, two test files):
Task: "T024 [P] [US1] FSM transition + conclude_phase_entered"
Task: "T025 [P] [US1] Tier 4 conclude delta in next assembly"
Task: "T026 [P] [US1] summarizer fires once after last conclude turn"
Task: "T027 [P] [US1] auto_pause_on_cap row + paused state"
Task: "T028 [P] [US1] adaptive cadence suspended"
Task: "T029 [P] [US1] skip-and-continue on conclude-turn provider error"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (V16 gate + schema + dataclasses + canary — all blocking)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Drive a Short-preset session through to auto-pause; verify the wrap-up artifact (summarizer output) is sound
5. Deploy / demo if ready (cap-only; mid-session cap-set, US3, US4, US13 deferred)

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 → MVP (cap → conclude → summarizer → pause; preset-driven only at session-create)
3. US2 → mid-session cap-set + disambiguation; OR semantics fully exercised
4. US3 → cap-extension UX
5. US4 → manual-stop-during-conclude wrap-up preservation
6. US13 → spec 011 UI surfaces; end-to-end facilitator UX
7. Polish → V14 perf, integration test, quickstart walk-through

### Parallel Team Strategy

With multiple developers after Phase 2:

- Developer A: US1 (P1 MVP)
- Developer B: US2 (P1 cap-set + disambiguation; can land in parallel with US1 once T032 helpers exist)
- Developer C: US13 frontend prep (UMD module scaffolds T081, T084, T086 — pure frontend, no backend dependency until WS emitters land)

Stories integrate at Polish phase. US3 and US4 are sequential after US1+US2 since they're small and reuse the same FSM hooks.

---

## Notes

- [P] tasks = different files OR independent functions in the same file with no shared edit point (e.g., five validator functions in `src/config/validators.py` are P; the `VALIDATORS` tuple append is not)
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing (the SC-001 canary is the foundational example)
- Per memory `feedback_test_schema_mirror`: alembic migration + `tests/conftest.py` raw DDL update MUST land in the same task (T016) — CI builds schema from conftest, not migrations
- Per memory `frontend_polish_module_pattern`: UI components in US13 ship as UMD modules under [frontend/](frontend/) with Node-runnable unit tests under [tests/frontend/](tests/frontend/) plus Playwright e2e
- Per memory `feedback_no_auto_push`: do not push the branch upstream without explicit confirmation
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence (US3, US4, US13 all depend on US1 + US2 by design — those dependencies are explicit in the dependency graph above and not hidden)
