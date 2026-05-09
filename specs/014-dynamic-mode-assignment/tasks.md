# Tasks: Dynamic Mode Assignment (Signal-Driven Controller for High-Traffic Mode)

**Input**: Design documents from `/specs/014-dynamic-mode-assignment/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (audit-events, signal-source-interface, env-vars), quickstart.md

**V16 deliverable gate**: validators for the six new `SACP_DMA_*` / `SACP_AUTO_MODE_ENABLED` env vars + their `docs/env-vars.md` sections + `tests/test_014_validators.py` are ALREADY landed on this branch in commit `5de8df8` ("Land spec 014 V16 env-var deliverables"). They are NOT scheduled below — they were the gate satisfied before `/speckit.tasks` per spec FR-014.

**Schema-mirror non-task**: spec 014 introduces no schema change (five new event types reuse `admin_audit_log` per data-model.md §"DB-persistent audit shapes"). The conftest schema-mirror discipline (any alembic-added column also added to `tests/conftest.py` raw DDL) is therefore not load-bearing for this spec.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User-story phase tasks only (US1, US2, US3). Setup, Foundational, and Polish phases carry no story label.
- File paths are absolute relative to repo root.

## Path Conventions

- Single Python service. Source under `src/`, tests under `tests/`. Layout matches plan.md §"Project Structure":
  - `src/orchestrator/dma_controller.py`, `src/orchestrator/dma_signals.py` — new submodules.
  - `src/orchestrator/high_traffic.py`, `src/orchestrator/convergence.py` — surgical hook edits.
  - `src/repositories/log_repo.py` — extend with mode_* audit-event helpers.
  - `tests/test_014_*.py` — five test modules per plan.md test layout.
  - `tests/conftest.py` — extend with synthetic-signal fixtures.

---

## Phase 1: Setup

**Purpose**: Confirm the controller source tree is reachable from the existing layout. Minimal because `src/`, `tests/`, and config infrastructure are established.

- [X] T001 Add empty module stubs `src/orchestrator/dma_controller.py` and `src/orchestrator/dma_signals.py` with module docstrings cross-referencing this spec, so imports resolve before downstream tasks land logic.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Hooks, scaffolding, and the SC-004 regression canary that must land before any user-story phase begins.

**CRITICAL**: No user-story task may begin until Phase 2 is complete. The regression test (T002) is the canary — if it ever fails after Phase 2, the additive-when-unset guarantee (FR-015 + SC-004) has been broken.

- [X] T002 Add SC-004 regression canary in `tests/test_014_regression_spec013_only.py`: re-run spec-013's acceptance scenarios with all `SACP_DMA_*` and `SACP_AUTO_MODE_ENABLED` env vars unset; assert no controller task spawns, no `mode_*` audit rows are written, and spec-013 baseline behavior is unchanged.
- [X] T003 Add `last_similarity` read-only property on `ConvergenceEngine` in `src/orchestrator/convergence.py`; set the backing `_last_similarity` field at the existing similarity-computation point (line ~177 per research §2). Single-line addition; no behavior change for non-014 callers.
- [X] T004 Extend `HighTrafficSessionConfig` in `src/orchestrator/high_traffic.py` with controller-only mutator methods `engage_mechanism(name)` and `disengage_mechanism(name)` per research §4. Each spec-013 mechanism call-site reads `(config is not None) AND mechanism.is_active(name)`; default state mirrors spec-013 baseline so unset env vars stay structurally disabled.
- [X] T005 [P] Define the `SignalSource` Protocol in `src/orchestrator/dma_signals.py` per `contracts/signal-source-interface.md` (name, is_configured, is_available, sample, threshold, evaluate). No concrete adapters yet — those land per-story.
- [X] T006 [P] Implement `SessionSignals` ring-buffer container in `src/orchestrator/dma_controller.py` per data-model.md §"SessionSignals": four bounded buffers, append-and-evict on overflow, sized at `window_seconds / decision_cycle_interval_seconds = 60` entries per source.
- [X] T007 [P] Implement `ControllerState` dataclass in `src/orchestrator/dma_controller.py` per data-model.md §"ControllerState": last_emitted_action, last_transition_at, dwell_floor_at, signal_health, unavailability_emitted_in_dwell.
- [X] T008 Implement `DecisionCycleBudget` token-bucket throttle in `src/orchestrator/dma_controller.py` per research §5: capacity-1 bucket with `60.0 / cap_per_minute` refill interval, monotonic-clock-based, `try_acquire()` returns False when not yet eligible.
- [X] T009 Add `mode_*` audit-event helpers in `src/repositories/log_repo.py` for the five new action strings (`mode_recommendation`, `mode_transition`, `mode_transition_suppressed`, `decision_cycle_throttled`, `signal_source_unavailable`) per `contracts/audit-events.md` row contracts. Reuse existing `admin_audit_log` append-only path.
- [X] T010 Add topology-7 forward-proof gate in `src/orchestrator/dma_controller.py`: `start()` reads `SACP_TOPOLOGY` and skips controller spawn when value is `7` per research §7. One-time INFO log; no `SACP_DMA_*` env-var validation suppression.
- [X] T011 Extend `tests/conftest.py` with synthetic-signal fixtures (no real ML inference): controllable per-signal value injectors for turn rate, similarity, queue depth, and density-anomaly count. Required by every Phase-3+ test before it can drive deterministic signal trajectories.

**Checkpoint**: Foundation ready. T002 canary passes (controller is inactive when unconfigured). User-story phases can now proceed in priority order.

---

## Phase 3: User Story 1 - Advisory recommendations surface to facilitator (Priority: P1) — MVP

**Goal**: The controller observes session signals, decides ENGAGE/DISENGAGE at a rate-capped cadence, and emits `mode_recommendation` audit events when the action changes — without altering any spec-013 mechanism state.

**Independent Test**: Launch a session with `SACP_DMA_TURN_RATE_THRESHOLD_TPM=30` and `SACP_AUTO_MODE_ENABLED` unset. Drive turn rate above threshold for the observation window. Assert exactly one `mode_recommendation` row with `action=ENGAGE`, the populated triggers/observations/dwell_floor fields, and zero spec-013 mechanism state changes.

- [X] T012 [US1] Implement `TurnRateSignal` adapter in `src/orchestrator/dma_signals.py` (canonical Phase 3 signal) per `contracts/signal-source-interface.md`: name="turn_rate", samples turns-in-prior-minute from the loop's per-turn callback, evaluates `mean(window) >= threshold`.
- [X] T013 [US1] Implement controller decision-cycle in `src/orchestrator/dma_controller.py`: poll configured signal sources, apply FR-009 asymmetry (ANY trigger above threshold → ENGAGE; ALL configured below for dwell → DISENGAGE; else carry last action), and dedupe per research §6 (emit only on action change).
- [X] T014 [US1] Implement `ModeRecommendation` emission path in `src/orchestrator/dma_controller.py` writing to `admin_audit_log` via the helper from T009. Always populate `dwell_floor_at` even in advisory mode (informational per data-model.md).
- [X] T015 [US1] Wire controller task lifecycle into `src/orchestrator/loop.py` per research §3: spawn `dma_controller.start(session_id, config, signals_provider)` after `HighTrafficSessionConfig` resolves and `ConvergenceEngine` constructs; cancel on session teardown.
- [X] T016 [US1] Enforce FR-011 advisory-mode boundary in `src/orchestrator/dma_controller.py`: when `SACP_AUTO_MODE_ENABLED` is unset/false, the recommendation path MUST NOT call `engage_mechanism` / `disengage_mechanism` and MUST NOT write `mode_transition` rows.
- [X] T017 [US1] Add advisory-mode acceptance tests in `tests/test_014_advisory_mode.py` covering all three spec acceptance scenarios: ENGAGE on sustained over-threshold turn rate, DISENGAGE after sustained under-threshold + dwell, and inactive controller when no `SACP_DMA_*` thresholds are set.

**Checkpoint**: US1 is fully functional in isolation. The controller emits recommendations without touching spec-013 state. This is the MVP — deployable to Phase 3 advisory-mode-only.

---

## Phase 4: User Story 2 - Auto-apply behind feature flag (Priority: P2)

**Goal**: When `SACP_AUTO_MODE_ENABLED=true`, the controller engages/disengages spec-013 mechanisms and emits `mode_transition` events governed by `SACP_DMA_DWELL_TIME_S` hysteresis. Suppressed transitions emit `mode_transition_suppressed`.

**Independent Test**: Launch a session with `SACP_AUTO_MODE_ENABLED=true` plus the same threshold/dwell config as US1. Drive turn rate above threshold; assert one `mode_transition` row with `action=ENGAGE`, configured spec-013 mechanisms become active, and the matched `engaged_mechanisms[]` / `skipped_mechanisms[]` fields populate. Drive turn rate below threshold during dwell; assert `mode_transition_suppressed` with `reason=dwell_floor_not_reached`.

- [X] T018 [US2] Implement auto-apply transition path in `src/orchestrator/dma_controller.py`: when `SACP_AUTO_MODE_ENABLED=true` AND a recommendation fires AND dwell-floor permits, invoke `HighTrafficSessionConfig.engage_mechanism` / `disengage_mechanism` for each spec-013 mechanism whose env var is set. Mechanisms with unset env vars list in `skipped_mechanisms[]` per spec edge case.
- [X] T019 [US2] Implement dwell-floor hysteresis in `src/orchestrator/dma_controller.py` per FR-007: track `last_transition_at`; reject counter-direction transitions until `last_transition_at + SACP_DMA_DWELL_TIME_S` elapses AND the underlying signal condition has been sustained for the full dwell window.
- [X] T020 [US2] Implement `ModeTransition` emission in `src/orchestrator/dma_controller.py` via the T009 helper. Pair every transition with its corresponding `mode_recommendation` row at the same `decision_at` per `contracts/audit-events.md`.
- [X] T021 [US2] Implement `ModeTransitionSuppressed` emission in `src/orchestrator/dma_controller.py` per FR-008: when auto-apply would have fired but dwell blocks, write the suppressed-row with `reason=dwell_floor_not_reached` and the `eligible_at` timestamp.
- [X] T022 [US2] Add FR-010 cross-validator integration test in `tests/test_014_auto_apply.py`: `SACP_AUTO_MODE_ENABLED=true` with `SACP_DMA_DWELL_TIME_S` unset MUST fail orchestrator startup with a clear error naming both vars (the cross-validator already lives in `src/config/validators.py` per V16; this test asserts the boot-time exit).
- [X] T023 [US2] Add auto-apply acceptance tests in `tests/test_014_auto_apply.py` covering all four spec acceptance scenarios: ENGAGE transition with spec-013 mechanism activation, dwell-blocked counter-direction transition emitting `mode_transition_suppressed`, post-dwell DISENGAGE transition reverting mechanisms, and the FR-010 startup-exit case (cross-link to T022).

**Checkpoint**: US1 + US2 both work independently. Operators can promote a deployment from advisory to auto-apply per quickstart.md Step 3.

---

## Phase 5: User Story 3 - Signal sources independently configurable (Priority: P3)

**Goal**: All four signal sources are independently configurable, independently testable, and independently disable-able. Unavailable sources contribute nothing and emit at most one rate-limited `signal_source_unavailable` audit event per dwell window per signal.

**Independent Test**: Launch four separate sessions, each with exactly one of the four `SACP_DMA_*_THRESHOLD` vars set. For each, drive the corresponding signal above its threshold and assert the `mode_recommendation` names that signal as the `trigger` field while unset signals appear in no audit event.

- [X] T024 [P] [US3] Implement `ConvergenceDerivativeSignal` adapter in `src/orchestrator/dma_signals.py` per `contracts/signal-source-interface.md`: reads `ConvergenceEngine.last_similarity` (T003 hook), evaluates `abs(window[-1] - window[0]) >= threshold`.
- [X] T025 [P] [US3] Implement `QueueDepthSignal` adapter in `src/orchestrator/dma_signals.py` per `contracts/signal-source-interface.md`: reads spec-013 batching's per-recipient queue sizes, evaluates `max(window) >= threshold` (spike-sensitive). Inactive when batching is unconfigured or in topology 5.
- [X] T026 [P] [US3] Implement `DensityAnomalySignal` adapter in `src/orchestrator/dma_signals.py` per `contracts/signal-source-interface.md` and research §1: count `convergence_log` rows with `tier='density_anomaly'` produced in the prior minute (sliding count); evaluates `mean(window) >= threshold`.
- [X] T027 [US3] Enforce FR-004 absent-not-zero semantic in `src/orchestrator/dma_controller.py`: each decision cycle iterates only over signal sources whose `is_configured()` returns True. A signal whose threshold env var is unset MUST contribute nothing — not zero, not infinity, absent.
- [X] T028 [US3] Implement `signal_source_unavailable` rate-limited emission in `src/orchestrator/dma_controller.py` per FR-013: at most one row per dwell window per signal per session, gated by `ControllerState.unavailability_emitted_in_dwell`. Emit via the T009 helper.
- [X] T029 [US3] Implement `triggers[]` alphabetical ordering in `src/orchestrator/dma_controller.py` per spec acceptance scenario 3: when multiple signals cross simultaneously in the same observation window, the `mode_recommendation` payload sorts trigger names alphabetically with `signal_observations[]` in matching order.
- [X] T030 [US3] Add per-signal-independence acceptance tests in `tests/test_014_signal_independence.py` covering the four scenarios: turn-rate-only triggers `trigger=turn_rate`, convergence-only triggers `trigger=convergence_derivative`, simultaneous multi-trigger lists alphabetically, and unavailable source emits one rate-limited `signal_source_unavailable` event then stays silent within dwell.

**Checkpoint**: All three user stories are independently functional. Operators can roll out signals incrementally per quickstart.md Step 2.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: V14 instrumentation, throttle observability, density-anomaly definition refinement, topology-7 forward-proof verification, quickstart validation, and doc cross-references.

- [X] T031 Add per-cycle and per-signal `routing_log` instrumentation in `src/orchestrator/dma_controller.py` and `src/orchestrator/dma_signals.py` per FR-012 + spec-003 §FR-030: stage `dma_controller_eval_ms` for the full cycle and `dma_signal_<name>_ms` for each adapter's `sample()` + `evaluate()`. Reuse the existing `@with_stage_timing` decorator.
- [X] T032 [P] Implement `decision_cycle_throttled` rate-limited emission in `src/orchestrator/dma_controller.py` per FR-013: when `DecisionCycleBudget.try_acquire()` returns False, emit at most one `decision_cycle_throttled` audit row per dwell window per session via the T009 helper.
- [X] T033 [P] Add throttle + unavailability stress tests in `tests/test_014_throttle_and_unavailability.py`: oscillate signals faster than 12 dpm and assert `cap * minutes_observed` recommendations cap (SC-009); make a signal source permanently unavailable and assert exactly one `signal_source_unavailable` row per dwell window (SC-009 + FR-013).
- [ ] T034 Refine the density-anomaly definition in `src/orchestrator/dma_signals.py` if research-§1 discrimination proves insufficient on real session data. Default heuristic per research §1 is the simple sliding count; tighten only if operator feedback shows the count is too noisy. Document any change in `specs/014-dynamic-mode-assignment/research.md`. _Deferred — initial heuristic in place; refinement requires real session data not yet available._
- [X] T035 Verify topology-7 forward-proof gate end-to-end: with `SACP_TOPOLOGY=7` set, assert no controller task spawns, no `SACP_DMA_*` env-var validation occurs at the controller-init path, and a one-time INFO log emits per research §7. Test in `tests/test_014_throttle_and_unavailability.py`.
- [ ] T036 Run `quickstart.md` step-by-step against a local orchestrator: enable advisory mode, add signals, promote to auto-apply, observe flap-tuning behavior, query the audit log for all five new event types, and confirm the disable/rollback path returns to spec-013-only baseline (SC-004 cross-check). _Deferred — operator-driven step requiring a running orchestrator, not in-band for agent implementation._
- [X] T037 Verify `docs/env-vars.md` cross-references for the six 014 env vars match the V16 deliverable already on this branch (commit `5de8df8`): each entry has Default, Type, Valid range, Blast radius, Validation rule, Source spec; `SACP_AUTO_MODE_ENABLED` calls out the operator-trust prerequisite per `contracts/env-vars.md`. Update only if drift is found. _Verified: all six entries present at docs/env-vars.md lines 294-342 with correct Type / Valid range / Validation rule / Source spec / Cross-validator notes; no drift._

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 (Setup): no dependencies; can start immediately.
- Phase 2 (Foundational): depends on Phase 1; BLOCKS all user stories. T002 (the SC-004 canary) lands first within Phase 2 so the additive-when-unset contract is enforced from the moment any controller code lands.
- Phase 3 (US1): depends on Phase 2 complete.
- Phase 4 (US2): depends on Phase 2 complete; integrates with US1 hooks (T018 reuses T013's decision-cycle path) but is testable independently via auto-apply-only fixtures.
- Phase 5 (US3): depends on Phase 2 complete; the `TurnRateSignal` from US1 (T012) is the canonical first signal and T024–T026 add the others independently.
- Phase 6 (Polish): depends on US1 complete at minimum; T032–T033 also depend on US3's signal adapters being landed.

### Within-Phase Dependencies

- T003 + T004 (the spec-004 + spec-013 hooks) precede T015 (loop integration), T012 (turn-rate adapter), T018 (auto-apply), and T024 (convergence-derivative adapter).
- T005 (Protocol) precedes all four adapters (T012, T024, T025, T026).
- T006 + T007 (state + buffer) precede T013 (decision cycle).
- T008 (throttle) precedes T032 (throttle audit emission).
- T009 (audit-event helpers) precedes every emission task: T014, T020, T021, T028, T032.
- T011 (synthetic-signal fixtures) precedes T017, T023, T030, T033.
- T013 (decision cycle) precedes T014, T016, T018, T019, T027, T029.

### Parallel Opportunities

- **Within Phase 2**: T005, T006, T007 all touch independent regions — Protocol declaration, ring-buffer dataclass, and ControllerState dataclass live in different definition blocks within `dma_signals.py` / `dma_controller.py` and can land concurrently. T002 (the canary test) and T011 (conftest fixtures) are also parallelizable with each other.
- **Within Phase 5**: T024, T025, T026 are the three non-canonical signal adapters. Each is a self-contained class in `dma_signals.py`. They can land in parallel branches if multiple developers work US3 simultaneously — the spec specifically calls out per-signal independence as the design property that enables this.
- **Within Phase 6**: T032 and T033 (throttle audit + throttle test) parallelize with T034–T037 (density refinement, topology-7 verification, quickstart validation, doc cross-ref check) — different files, no inter-task dependencies.

---

## Parallel Example: User Story 3

```bash
# Three signal adapters can land concurrently — each is a separate class
# inside src/orchestrator/dma_signals.py with no cross-adapter calls
# (per contracts/signal-source-interface.md "No cross-signal coupling").

Task: "Implement ConvergenceDerivativeSignal adapter in src/orchestrator/dma_signals.py"
Task: "Implement QueueDepthSignal adapter in src/orchestrator/dma_signals.py"
Task: "Implement DensityAnomalySignal adapter in src/orchestrator/dma_signals.py"
```

Note: the three [P] adapters above all live in `dma_signals.py`. They parallelize because each is an independent class declaration with no inter-class calls; merge conflicts are limited to the file's import block and class registry, which the controller cycle (T013) imports via the Protocol contract rather than direct class names.

---

## Implementation Strategy

### MVP First (Setup + Foundational + US1 only)

1. Phase 1 — Setup (T001).
2. Phase 2 — Foundational (T002–T011), with T002 landing first as the SC-004 canary.
3. Phase 3 — US1 advisory mode (T012–T017).
4. **STOP and VALIDATE**: drive a Phase 3 session with `SACP_DMA_TURN_RATE_THRESHOLD_TPM=30` and confirm `mode_recommendation` events emit per US1 acceptance scenarios. This is the deployable MVP — advisory mode only, no auto-apply, no spec-013 mechanism mutation.

### Incremental Delivery

1. Setup + Foundational → foundation ready, regression canary green.
2. US1 advisory mode → MVP, deploy to Phase 3 staging. Operators observe recommendations across sessions to build trust.
3. US2 auto-apply (behind `SACP_AUTO_MODE_ENABLED=false` default) → operators opt in per-deployment after advisory observation.
4. US3 multi-signal → operators add convergence-derivative, queue-depth, and density-anomaly signals incrementally per quickstart.md Step 2.
5. Polish — V14 instrumentation, throttle audit emission, density refinement, topology-7 verification, quickstart validation.

### Parallel Team Strategy

After Phase 2 lands:

- Developer A: Phase 3 (US1) — turn-rate adapter, decision cycle, recommendation emission.
- Developer B: Phase 4 (US2) — auto-apply path, dwell hysteresis, transition emission. Depends on T013 from US1; can branch from US1's WIP once T013 is reviewable.
- Developer C: Phase 5 (US3) — three additional signal adapters. Independent of US1/US2 implementation order beyond the T005 Protocol from Phase 2.

The three [P] adapters in US3 (T024, T025, T026) further parallelize within Developer C's lane.

---

## Notes

- [P] markers reflect file-level independence: tasks marked [P] do not edit the same regions of the same files and have no dependency on each other's logic landing first.
- The SC-004 regression canary (T002) is foundational and runs throughout all subsequent phases — any task whose change makes T002 fail has broken the additive-when-unset contract.
- The V16 env-var deliverables (validators in `src/config/validators.py`, `docs/env-vars.md` sections, `tests/test_014_validators.py`) are NOT in this list. They landed pre-`/speckit.tasks` per FR-014 (commit `5de8df8` on this branch).
- No alembic migration is required; the five new audit event types reuse the existing `admin_audit_log` schema. The conftest schema-mirror discipline is therefore not load-bearing for this spec.
- Each user story should be independently completable and testable per `.claude/skills/speckit-tasks/SKILL.md`. Stop at any checkpoint to validate the story in isolation.
