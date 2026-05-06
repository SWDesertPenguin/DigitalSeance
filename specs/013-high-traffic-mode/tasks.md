---

description: "Task list for implementing spec 013 (high-traffic session mode / broadcast)"
---

# Tasks: High-Traffic Session Mode (Broadcast Mode)

**Input**: Design documents from `/specs/013-high-traffic-mode/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — spec defines three Independent Tests + ten Acceptance Scenarios across US1–US3, and plan.md enumerates test files per story. Tests land alongside implementation.

**Organization**: Tasks grouped by user story so each can be implemented and tested independently. Phase 2 covers shared infrastructure (V16 deliverable gate per FR-014). The SC-005 regression scaffold lands EARLY in Phase 2 as a canary for the additive-when-unset guarantee.

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (no label for Setup, Foundational, Polish)

## Path Conventions

Single project, paths under repo root. `src/orchestrator/` and `tests/` per spec 013 plan.md project structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repo hygiene + new module placeholders. Working tree should already be on `013-high-traffic-mode` branch off main.

- [ ] T001 Verify on branch `013-high-traffic-mode` and run `python -m src.run_apps --validate-config-only` to confirm V16 baseline before any code changes
- [ ] T002 [P] Create empty module skeletons: `src/orchestrator/high_traffic.py`, `src/orchestrator/observer_downgrade.py`, `src/web_ui/batch_scheduler.py` (each containing only a module docstring referencing spec 013)

---

## Phase 2: Foundational (Blocking Prerequisites — V16 Gate per FR-014)

**Purpose**: V16 env-var deliverables + shared `HighTrafficSessionConfig` infrastructure. All three user stories depend on these.

**⚠️ CRITICAL**: No user-story task in Phase 3+ may begin until Phase 2 completes. The V16 gate is non-negotiable per spec FR-014.

- [ ] T003 [P] Add `validate_high_traffic_batch_cadence_s` to [src/config/validators.py](src/config/validators.py) (positive int, `[1, 300]`)
- [ ] T004 [P] Add `validate_convergence_threshold_override` to [src/config/validators.py](src/config/validators.py) (float, strict `(0.0, 1.0)`)
- [ ] T005 [P] Add `validate_observer_downgrade_thresholds` to [src/config/validators.py](src/config/validators.py) (composite parser per [research.md §2](specs/013-high-traffic-mode/research.md): required keys `participants` ∈ [2,10], `tpm` ∈ [1,600]; optional `restore_window_s` ∈ [1,3600] default 120; unknown keys + missing required keys + out-of-range values all exit at startup)
- [ ] T006 Append the three new validators to the `VALIDATORS` tuple in [src/config/validators.py](src/config/validators.py)
- [ ] T007 [P] Add `### SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields per [contracts/env-vars.md](specs/013-high-traffic-mode/contracts/env-vars.md)
- [ ] T008 [P] Add `### SACP_CONVERGENCE_THRESHOLD_OVERRIDE` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields
- [ ] T009 [P] Add `### SACP_OBSERVER_DOWNGRADE_THRESHOLDS` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields
- [ ] T010 Run `python scripts/check_env_vars.py` from repo root and confirm `env-vars: OK (24 vars in src/, 26 sections in docs)` (V16 CI gate green for the three new vars)
- [ ] T011 Implement `HighTrafficSessionConfig` frozen dataclass in [src/orchestrator/high_traffic.py](src/orchestrator/high_traffic.py) per [data-model.md §HighTrafficSessionConfig](specs/013-high-traffic-mode/data-model.md): fields `batch_cadence_s: int | None`, `convergence_threshold_override: float | None`, `observer_downgrade: ObserverDowngradeThresholds | None`
- [ ] T012 Implement `ObserverDowngradeThresholds` frozen dataclass in [src/orchestrator/high_traffic.py](src/orchestrator/high_traffic.py) per [data-model.md §ObserverDowngradeThresholds](specs/013-high-traffic-mode/data-model.md): fields `participants: int`, `tpm: int`, `restore_window_s: int`
- [ ] T013 Implement `HighTrafficSessionConfig.resolve_from_env() -> HighTrafficSessionConfig | None` classmethod in [src/orchestrator/high_traffic.py](src/orchestrator/high_traffic.py) — returns `None` when ALL three env vars unset (per SC-005 regression contract)
- [ ] T014 Wire `HighTrafficSessionConfig.resolve_from_env()` into the session-init path of [src/orchestrator/loop.py](src/orchestrator/loop.py); store the resolved config (or `None`) on the loop's session-runtime context
- [ ] T015 Add the SC-005 regression-scaffold test file at [tests/test_013_regression_phase2.py](tests/test_013_regression_phase2.py) with 6 stubbed scenarios per [research.md §6](specs/013-high-traffic-mode/research.md) (1. solo turn-loop no envelope, 2. multi-AI global-threshold convergence, 3. circuit-breaker pause without downgrade interference, 4. review-gate per-turn drafts, 5. state-change immediate broadcast, 6. routing-log shape unchanged); stubs assert `True` until each US lands

**Checkpoint**: V16 gate green; `HighTrafficSessionConfig` resolvable; SC-005 canary in place. User-story phases unblocked.

---

## Phase 3: User Story 1 — Batching cadence (Priority: P1) 🎯 MVP

**Goal**: AI-to-human messages coalesce into batched envelopes on the configured cadence, keeping `review_gate` consultants productive when AI exchange rate spikes.

**Independent Test**: Launch 3-participant session (1 human review_gate + 2 AI) with `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S=15`. Drive AI exchanges above threshold. Verify human receives batched envelopes every ~15s, no message held longer than 20s (cadence + 5s).

### Tests for User Story 1

- [ ] T016 [P] [US1] Acceptance scenario 1 (4 turns in 10s → one batched delivery within 20s) in [tests/test_013_batching.py](tests/test_013_batching.py)
- [ ] T017 [P] [US1] Acceptance scenario 2 (1 turn alone → still delivered within cadence + 5s) in [tests/test_013_batching.py](tests/test_013_batching.py)
- [ ] T018 [P] [US1] Acceptance scenario 3 (env var unset → per-turn delivery, no envelope event) in [tests/test_013_batching.py](tests/test_013_batching.py)
- [ ] T019 [P] [US1] State-change bypass test: convergence event during open envelope → emitted immediately, not wrapped (FR-004; [contracts/batch-envelope.md §Bypass rule](specs/013-high-traffic-mode/contracts/batch-envelope.md))
- [ ] T020 [P] [US1] Cadence + 5s slack test: scheduler tick missed → hard close at `opened_at + cadence + 5s` (FR-003 budget)

### Implementation for User Story 1

- [ ] T021 [P] [US1] Implement `BatchEnvelope` dataclass in [src/web_ui/batch_scheduler.py](src/web_ui/batch_scheduler.py) per [data-model.md §BatchEnvelope](specs/013-high-traffic-mode/data-model.md)
- [ ] T022 [US1] Implement `BatchScheduler` per-session flush task in [src/web_ui/batch_scheduler.py](src/web_ui/batch_scheduler.py): one in-process queue keyed by `(session_id, recipient_id)`, cadence-tick flush, hard-close at slack budget
- [ ] T023 [US1] Implement `batch_envelope_event(envelope: BatchEnvelope)` event-builder in [src/web_ui/events.py](src/web_ui/events.py) (websocket event shape per [contracts/batch-envelope.md](specs/013-high-traffic-mode/contracts/batch-envelope.md))
- [ ] T024 [US1] Wire enqueue path: when `HighTrafficSessionConfig.batch_cadence_s is not None` AND target is human, AI-to-human messages route through `BatchScheduler.enqueue` in [src/orchestrator/loop.py](src/orchestrator/loop.py); state-change events bypass per FR-004
- [ ] T025 [US1] Wire BatchScheduler lifecycle into [src/orchestrator/loop.py](src/orchestrator/loop.py) session-init/teardown (spawn flush task on session-start when `batch_cadence_s is not None`; cancel on session teardown)
- [ ] T026 [US1] Capture `batch_open_ts` and `batch_close_ts` per emitted envelope into `routing_log` per spec 003 §FR-030; reuse `@with_stage_timing` from [src/orchestrator/timing.py](src/orchestrator/timing.py)

**Checkpoint**: US1 functional and testable independently. SC-001 (queue depth bounded) + SC-002 (P95 ≤ cadence + 5s) verifiable; SC-007 (operator workflow ≤ 5 minutes) walkthrough-testable.

---

## Phase 4: User Story 2 — Convergence-threshold override (Priority: P2)

**Goal**: Per-session override of the global convergence threshold so 4-participant high-traffic sessions don't declare premature convergence.

**Independent Test**: Launch session with global `SACP_CONVERGENCE_THRESHOLD=0.70` and per-session `SACP_CONVERGENCE_THRESHOLD_OVERRIDE=0.85`. Drive to similarity 0.75 — engine does NOT declare convergence. Drive to 0.86 — engine declares convergence using override.

### Tests for User Story 2

- [ ] T027 [P] [US2] Acceptance scenario 1 (override 0.85 + similarity 0.75 → no convergence declaration) in [tests/test_013_convergence_override.py](tests/test_013_convergence_override.py)
- [ ] T028 [P] [US2] Acceptance scenario 2 (override 0.85 + similarity 0.86 → convergence declared) in [tests/test_013_convergence_override.py](tests/test_013_convergence_override.py)
- [ ] T029 [P] [US2] Acceptance scenario 3 (out-of-range override → V16 startup exit) in [tests/test_013_convergence_override.py](tests/test_013_convergence_override.py)
- [ ] T030 [P] [US2] Acceptance scenario 4 (override unset → engine reads global threshold unchanged; SC-003 constant-time guarantee) in [tests/test_013_convergence_override.py](tests/test_013_convergence_override.py)

### Implementation for User Story 2

- [ ] T031 [US2] In [src/orchestrator/loop.py](src/orchestrator/loop.py) session-init path, when `HighTrafficSessionConfig.convergence_threshold_override is not None` pass that value to `ConvergenceEngine(threshold=...)`; otherwise pass the existing global default (no engine refactor — uses existing constructor parameter per [research.md §5](specs/013-high-traffic-mode/research.md))

**Checkpoint**: US2 functional. SC-003 verifiable: routing_log shows no per-turn override-resolution stage row.

---

## Phase 5: User Story 3 — Observer-downgrade (Priority: P3)

**Goal**: When participant count or turn rate spikes past configured thresholds, transparently downgrade the lowest-priority active participant to observer; restore when traffic subsides; never silently downgrade the last human.

**Independent Test**: Launch 5-participant session with thresholds `participants:4,tpm:30`. Drive turn rate to 35 tpm. Verify exactly one downgrade fires + audit row written. Drop turn rate below 25 tpm sustained — verify restore + audit row.

### Tests for User Story 3

- [ ] T032 [P] [US3] Acceptance scenario 1 (5-participant + 35 tpm + thresholds tripped → downgrade lowest-priority + audit row) in [tests/test_013_observer_downgrade.py](tests/test_013_observer_downgrade.py)
- [ ] T033 [P] [US3] Acceptance scenario 2 (sustained drop below threshold → restore + audit row) in [tests/test_013_observer_downgrade.py](tests/test_013_observer_downgrade.py)
- [ ] T034 [P] [US3] Acceptance scenario 3 (env var unset/invalid → no downgrades; preserve Phase 2 baseline) in [tests/test_013_observer_downgrade.py](tests/test_013_observer_downgrade.py)
- [ ] T035 [P] [US3] Acceptance scenario 4 (per-turn evaluation cost captured in routing_log per FR-012) in [tests/test_013_observer_downgrade.py](tests/test_013_observer_downgrade.py)
- [ ] T036 [P] [US3] Last-human protection (FR-011): only-human candidate → suppression + `observer_downgrade_suppressed` audit row in [tests/test_013_observer_downgrade.py](tests/test_013_observer_downgrade.py)
- [ ] T037 [P] [US3] Priority heuristic test: composite `(model_tier, consecutive_timeouts desc, last_seen desc, id asc)` per [research.md §3](specs/013-high-traffic-mode/research.md) is deterministic in [tests/test_013_observer_downgrade.py](tests/test_013_observer_downgrade.py)
- [ ] T038 [P] [US3] Restore-window test: `tpm` below threshold for partial-window does NOT restore; full-window does (FR-010 sustained-low-traffic semantics) in [tests/test_013_observer_downgrade.py](tests/test_013_observer_downgrade.py)

### Implementation for User Story 3

- [ ] T039 [US3] Implement `lowest_priority_active(participants, exclude_paused=True) -> Participant | None` per [research.md §3](specs/013-high-traffic-mode/research.md) heuristic in [src/orchestrator/observer_downgrade.py](src/orchestrator/observer_downgrade.py)
- [ ] T040 [US3] Implement `evaluate_downgrade(session_state, config) -> DowngradeDecision` in [src/orchestrator/observer_downgrade.py](src/orchestrator/observer_downgrade.py): reads `participants` count + `tpm` from session state; applies last-human protection; returns one of `Downgrade(participant, reason)` / `Suppressed(participant, reason)` / `NoOp`
- [ ] T041 [US3] Implement `evaluate_restore(session_state, config, last_downgrade_at) -> RestoreDecision` in [src/orchestrator/observer_downgrade.py](src/orchestrator/observer_downgrade.py): tracks sustained-low-traffic window per FR-010
- [ ] T042 [US3] Audit-row writers in [src/orchestrator/observer_downgrade.py](src/orchestrator/observer_downgrade.py) — three `admin_audit_log` action strings (`observer_downgrade`, `observer_restore`, `observer_downgrade_suppressed`) per [contracts/audit-events.md](specs/013-high-traffic-mode/contracts/audit-events.md). Audit-row write happens BEFORE role state mutation (transactional consistency requirement)
- [ ] T043 [US3] Wire downgrade evaluator into [src/orchestrator/loop.py](src/orchestrator/loop.py) turn-prep phase: call `evaluate_downgrade` only when `HighTrafficSessionConfig.observer_downgrade is not None`; apply role mutation atomically with audit write
- [ ] T044 [US3] Wire `evaluate_restore` into the same turn-prep phase, after evaluate_downgrade; restore eligibility checked against the session's last `observer_downgrade` timestamp
- [ ] T045 [US3] Capture per-turn `observer_downgrade_eval_ms` stage timing into `routing_log` (FR-012 / SC-004) using `@with_stage_timing`

**Checkpoint**: US3 functional. SC-004 verifiable: O(participants) per-turn evaluation cost stays within turn-prep budget at participant counts up to 5.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Lock in regressions caught during implementation; finalize spec ceremony; update traceability + memory.

- [ ] T046 [P] Replace SC-005 stub assertions in [tests/test_013_regression_phase2.py](tests/test_013_regression_phase2.py) with full assertions for the 6 curated Phase 2 scenarios — should pass green when ALL three env vars unset
- [ ] T047 [P] Add 013 section to [docs/traceability/fr-to-test.md](docs/traceability/fr-to-test.md): one row per FR-001 through FR-015 mapping to its test in `tests/test_013_*.py` (or `untested` with trigger note)
- [ ] T048 [P] Add Clarifications entry to [specs/013-high-traffic-mode/spec.md](specs/013-high-traffic-mode/spec.md) per Constitution §14.7.5 amendment-PR pattern, recording the implementation details (env-var validators wired, audit shape reuses admin_audit_log, batch transport via single per-session flush task, priority heuristic shipped)
- [ ] T049 Run quickstart walkthrough per [specs/013-high-traffic-mode/quickstart.md](specs/013-high-traffic-mode/quickstart.md): enable each mechanism end-to-end against a local stack; confirm operator workflow ≤ 5 minutes per SC-007
- [ ] T050 Run full CI gate locally: `pytest tests/ --ignore=tests/e2e -q`, `ruff check src/ tests/`, `python scripts/lint_code_standards.py src/orchestrator/high_traffic.py src/orchestrator/observer_downgrade.py src/web_ui/batch_scheduler.py`, `python scripts/check_env_vars.py`, `python scripts/check_traceability.py` — all green
- [ ] T051 Status flip: edit [specs/013-high-traffic-mode/spec.md](specs/013-high-traffic-mode/spec.md) `**Status**: Draft (...)` line to `**Status**: Implemented (Phase 3 declaration: 2026-05-05; tasks landed: <date>)`. This unblocks spec 014's secondary gate per [014/spec.md line 60](specs/014-dynamic-mode-assignment/spec.md)

**Checkpoint**: 013 ready for merge. 014 unblocked.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately on the `013-high-traffic-mode` branch.
- **Foundational (Phase 2)**: Depends on Setup. **Blocks all user-story phases per FR-014 V16 deliverable gate.**
- **User Stories (Phase 3 / 4 / 5)**: All depend on Foundational completion.
  - Each story is independently testable per spec design (orthogonality contract).
  - May proceed in parallel if staffed; sequential P1 → P2 → P3 if not.
- **Polish (Phase 6)**: Depends on at least one user story complete; T046 and T051 specifically depend on all three.

### User Story Dependencies

- **US1 (P1, batching)**: Depends only on Phase 2 (`HighTrafficSessionConfig` + env-var validators + `BatchScheduler` placeholder).
- **US2 (P2, convergence override)**: Depends only on Phase 2. Single-line wiring change in `loop.py` plus tests.
- **US3 (P3, observer-downgrade)**: Depends on Phase 2. The most behaviorally complex of the three. Spec line 145–150 noted P3 because it benefits from US1+US2 landing first to inform threshold tuning, but no hard code dependency.

### Within Each User Story

- Tests written first (per the spec's explicit Acceptance Scenarios — assertions land before implementation makes them pass).
- Models / dataclasses before services.
- Services before integration into `loop.py` call-sites.
- Audit-row writers before role mutations (transactional consistency for US3).

### Parallel Opportunities

- T002, T003–T005, T007–T009, T011–T013 (foundational [P] tasks) can run in parallel.
- T016–T020 (US1 tests) can run in parallel.
- T021 BatchEnvelope dataclass is [P]; T022 BatchScheduler depends on T021 transitively.
- T027–T030 (US2 tests) can run in parallel.
- T032–T038 (US3 tests) can run in parallel.
- T039–T041 (US3 evaluator helpers) can run in parallel within `observer_downgrade.py`.
- T046–T048 (Polish [P] tasks) can run in parallel.

---

## Parallel Example: User Story 1 tests

```bash
# Launch all five US1 tests in parallel:
Task: "Acceptance scenario 1 — 4 turns in 10s → one batched delivery within 20s in tests/test_013_batching.py"
Task: "Acceptance scenario 2 — 1 turn alone → delivered within cadence+5s in tests/test_013_batching.py"
Task: "Acceptance scenario 3 — env var unset → per-turn delivery in tests/test_013_batching.py"
Task: "State-change bypass test in tests/test_013_batching.py"
Task: "Cadence+5s slack test in tests/test_013_batching.py"
```

## Parallel Example: V16 deliverable gate

```bash
# Launch the three validators + three doc sections in parallel:
Task: "Add validate_high_traffic_batch_cadence_s in src/config/validators.py"
Task: "Add validate_convergence_threshold_override in src/config/validators.py"
Task: "Add validate_observer_downgrade_thresholds in src/config/validators.py"
Task: "Add SACP_HIGH_TRAFFIC_BATCH_CADENCE_S section in docs/env-vars.md"
Task: "Add SACP_CONVERGENCE_THRESHOLD_OVERRIDE section in docs/env-vars.md"
Task: "Add SACP_OBSERVER_DOWNGRADE_THRESHOLDS section in docs/env-vars.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T015) — V16 gate green; SC-005 canary in place
3. Complete Phase 3: US1 batching (T016–T026)
4. **STOP and VALIDATE**: SC-001 + SC-002 green; consultants in `review_gate` no longer saturate on AI exchange spikes
5. Optional partial-shipment: a fix/* PR could close at Phase 3 if Phase 4/5 ship later (each story is independently valuable per spec design)

### Incremental Delivery

1. Phase 1 + Phase 2 → foundation ready; V16 gate green
2. Phase 3 (US1) → MVP, demoable to consulting use case
3. Phase 4 (US2) → adds research co-authorship convergence ergonomics
4. Phase 5 (US3) → adds graceful degradation under traffic spike
5. Phase 6 → finalize ceremony, flip status to Implemented, unblock spec 014

### Single-developer sequential

Run T001 → T051 in order. Each story phase ends at a clean checkpoint where the partial implementation is demoable.

---

## Notes

- [P] = different files, no incomplete-task dependencies.
- [Story] label maps task to its US for traceability and orthogonal-shipping option.
- Per Constitution §14.7.5 amendment-PR pattern: T048 records the Clarifications entry; the spec text itself stays Draft until T051 flips it to Implemented.
- SC-005 regression scaffold (T015 stub → T046 full) is the single most-important canary for the additive-when-unset guarantee. It must pass green at every checkpoint with all three env vars unset.
- Audit-event shape was chosen specifically to avoid a schema migration ([research.md §1](specs/013-high-traffic-mode/research.md)). If during implementation any task needs schema work, the spec ceremony has drifted from the plan — escalate before proceeding.
- Initial Phase 3 deployment for 013 is operator-opt-in by env var. Each mechanism enables independently; no single env var enables all three.
