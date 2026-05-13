---

description: "Task list for implementing spec 015 (provider failure detection — bridge-layer circuit breaker)"
---

# Tasks: Provider Failure Detection and Isolation (Bridge-Layer Circuit Breaker)

**Input**: Design documents from `/specs/015-provider-failure-detection/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — spec defines three Independent Tests + 19 Acceptance Scenarios across US1-US3 (plus 8 Edge Cases), and plan.md enumerates test files per story. Tests land alongside implementation.

**Organization**: Tasks grouped by user story so each can be implemented and tested independently. Phase 2 covers shared infrastructure (V16 deliverable gate per spec FR-014, schema migration with conftest mirror per memory `feedback_test_schema_mirror`). User-story phases follow.

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, OR independent functions in the same file with no shared edit point)
- **[Story]**: US1 / US2 / US3 (no label for Setup, Foundational, Polish)

## Path Conventions

Single project, paths under repo root. Backend code under [src/](src/); tests under [tests/](tests/) per [plan.md "Source Code"](specs/015-provider-failure-detection/plan.md).

---

## Phase 1: Setup

**Purpose**: Branch hygiene + prerequisite verification.

- [ ] T001 Verify working tree is on `015-provider-failure-detection` branch and `python -m src.run_apps --validate-config-only` passes before any new validators land (confirms V16 baseline is green)

---

## Phase 2: Foundational (Blocking Prerequisites -- V16 Gate per FR-014)

**Purpose**: V16 env-var deliverables (4 validators + 4 doc sections), schema migration with conftest mirror. All user stories depend on these.

**CRITICAL**: No user-story task in Phase 3+ may begin until Phase 2 completes. The V16 gate is non-negotiable per spec FR-014.

### V16 deliverable gate (4 validators + 4 doc sections)

- [ ] T002 [P] Add `validate_provider_failure_threshold` to [src/config/validators.py](src/config/validators.py): unset means inactive (return None); positive int in `[2, 100]`; out-of-range or non-integer exits at startup. Source spec: 015 §FR-014, §FR-015.
- [ ] T003 [P] Add `validate_provider_failure_window_s` to [src/config/validators.py](src/config/validators.py): unset means inactive (return None); positive int in `[30, 3600]`; out-of-range exits at startup. Source spec: 015 §FR-014, §FR-015.
- [ ] T004 [P] Add `validate_provider_recovery_probe_backoff` to [src/config/validators.py](src/config/validators.py): unset means no auto-recovery (return None); comma-separated list of 1-10 positive integers each in `[1, 600]`; any unparseable or out-of-range entry exits at startup. Source spec: 015 §FR-014.
- [ ] T005 [P] Add `validate_provider_probe_timeout_s` to [src/config/validators.py](src/config/validators.py): unset means inherit LiteLLM timeout (return None); positive int in `[1, 30]`; out-of-range exits at startup. Source spec: 015 §FR-014.
- [ ] T006 Add `validate_provider_failure_paired_vars` cross-validator to [src/config/validators.py](src/config/validators.py): fails if exactly one of `SACP_PROVIDER_FAILURE_THRESHOLD` / `SACP_PROVIDER_FAILURE_WINDOW_S` is set; both set or both unset is valid. Depends on T002-T003.
- [ ] T007 Append the five new validators to the `VALIDATORS` tuple at the bottom of [src/config/validators.py](src/config/validators.py) in order: T002, T003, T004, T005, T006 (cross-validator last). Depends on T002-T006.
- [ ] T008 [P] Add `### SACP_PROVIDER_FAILURE_THRESHOLD` section to [docs/env-vars.md](docs/env-vars.md) with six standard fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec)
- [ ] T009 [P] Add `### SACP_PROVIDER_FAILURE_WINDOW_S` section to [docs/env-vars.md](docs/env-vars.md) with six standard fields
- [ ] T010 [P] Add `### SACP_PROVIDER_RECOVERY_PROBE_BACKOFF` section to [docs/env-vars.md](docs/env-vars.md) with six standard fields -- note composite type (comma-separated), cycle-on-last semantics, unset = no auto-recovery
- [ ] T011 [P] Add `### SACP_PROVIDER_PROBE_TIMEOUT_S` section to [docs/env-vars.md](docs/env-vars.md) with six standard fields -- note unset = inherit LiteLLM timeout
- [ ] T012 Run `python scripts/check_env_vars.py` from repo root and confirm V16 CI gate green for the four new vars (validators + doc sections in lockstep). Depends on T007-T011.
- [ ] T013 [P] Validator unit tests in [tests/test_015_validators.py](tests/test_015_validators.py): each of the five validators -- valid value passes, out-of-range raises naming the offending var, unset returns None, cross-validator fires when exactly one of threshold/window is set

### Schema migration + conftest mirror (single landing per memory feedback_test_schema_mirror)

- [ ] T014 Generate alembic migration `023_circuit_breaker_audit.py` in [alembic/versions/](alembic/versions/) per [data-model.md](specs/015-provider-failure-detection/data-model.md): three append-only audit tables (`provider_circuit_open_log`, `provider_circuit_probe_log`, `provider_circuit_close_log`) with the columns and indexes in data-model.md. `down_revision = "021"`. AND mirror all three table DDLs into [tests/conftest.py](tests/conftest.py) raw schema in the same task. No `upgrade` / `downgrade` calls to existing tables -- pure additions.

**Checkpoint**: V16 gate green; schema migration + conftest mirror landed. User-story phases unblocked.

---

## Phase 3: User Story 1 -- Failing provider stops draining tokens (Priority: P1)

**Goal**: Full three-state `CircuitState` + `FailureRecord` ring buffer; `record_failure()` trips to open; `is_open()` returns True for open and half_open; short-circuit in loop.py; per-participant isolation.

### CircuitState + FailureRecord

- [ ] T015 Replace [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py) with the new module: `FailureRecord` frozen dataclass, `CircuitState` dataclass with all fields from [data-model.md](specs/015-provider-failure-detection/data-model.md), process-scope dict keyed on FR-001 tuple, `_compute_api_key_fingerprint()` helper (first 8 hex chars of SHA-256 of encrypted key).
- [ ] T016 Implement `record_failure(session_id, participant_id, provider, api_key_fingerprint, failure_kind)` in [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py): append FailureRecord to ring buffer; trim window; count in-window failures; if count >= threshold, transition closed -> open, write `provider_circuit_open_log` row async; return True if newly tripped else False. No-op (return False) when threshold or window env var is unset.
- [ ] T017 Implement `is_open(session_id, participant_id, provider, api_key_fingerprint)` in [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py): return True for state `open` or `half_open`; return False for `closed` or missing entry. Side effect: increment `consecutive_open_turns` when returning True.
- [ ] T018 Implement `short_circuit(session_id, participant_id, ...)` helper in [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py): handles the FR-005 skip semantics (log skip, handle consecutive_open_turns >= 3 -> auto-pause trigger) per existing §6.6 fallback policy.

### loop.py wiring

- [ ] T019 Update `_check_skip_conditions` in [src/orchestrator/loop.py](src/orchestrator/loop.py): replace `await breaker.is_open(speaker.id)` with `await breaker.is_open(session_id, speaker.id, speaker.provider, _fingerprint(speaker))`. Ensure the call returns early to `_skip_result(session_id, speaker.id, "circuit_open")` on True.
- [ ] T020 Update `_record_failure_and_announce` in [src/orchestrator/loop.py](src/orchestrator/loop.py): replace `await breaker.record_failure(speaker.id)` with `await breaker.record_failure(session_id, speaker.id, speaker.provider, _fingerprint(speaker), failure_kind)` where `failure_kind` is derived from `adapter.normalize_error(exc).category`. Depends on T015-T018.
- [ ] T021 Update `CircuitBreaker` instantiation site in [src/orchestrator/loop.py](src/orchestrator/loop.py): the new class no longer needs `pool` (in-memory state); remove the pool arg; pass the env-var-parsed threshold/window/backoff/probe_timeout at construction time. Confirm `record_success()` (existing call, if any) is updated or removed.

### US1 tests

- [ ] T022 [P] [tests/test_015_circuit_breaker.py](tests/test_015_circuit_breaker.py) -- SC acceptance tests:
  - US1 AS1: trip threshold -- participant's third failure within window trips to open; next `is_open()` returns True
  - US1 AS2: per-participant isolation -- participant B's `is_open()` returns False while participant A is tripped (SC-007)
  - US1 AS3: skipped turn per §6.6 policy -- skip result has `skip_reason='circuit_open'`; skip does not count toward convergence (FR-017)
  - US1 AS4: env vars unset -- `is_open()` always False; `record_failure()` is no-op; SC-005 regression contract
  - SC-008: startup-check contract test -- cross-identity LiteLLM fallback config triggers SystemExit at startup (FR-011)

---

## Phase 4: User Story 2 -- Provider recovery restores dispatch automatically (Priority: P2)

**Goal**: Backoff schedule parsing; probe task launch on open -> half_open; `validate_credentials()` probe; state transitions on probe outcome; cycle-on-last for exhausted schedule.

### Probe scheduler

- [ ] T023 Add `_schedule_next_probe(state: CircuitState)` in [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py): called from `is_open()` when state is `open` and backoff env var is set and the interval at `probe_schedule[probe_schedule_position]` has elapsed since last `opened_at`. Transitions to `half_open` and launches `asyncio.create_task(_run_probe(...))`. Guard: no new task if `_probe_task` is not None and not done.
- [ ] T024 Implement `_run_probe(state, adapter, decryption_key)` coroutine in [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py): call `asyncio.wait_for(adapter.validate_credentials(api_key, model), timeout=probe_timeout_s)`; on success transition to closed + write close log; on failure/timeout/exception transition back to open + write probe log; advance schedule position with cycle-on-last semantics; set `schedule_exhausted` flag on first probe of each cycle-restart.
- [ ] T025 Implement `_write_probe_log(...)` and `_write_close_log(...)` helpers in [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py): insert rows into the respective audit tables via the pool acquired at construction. Non-blocking (called from within `_run_probe` coroutine).

### api_key_update fast-close (FR-016)

- [ ] T026 Add `close_on_key_update(session_id, participant_id)` method to `CircuitBreaker` in [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py): finds all entries matching `(session_id, participant_id)` regardless of fingerprint; cancels in-flight probe task if any; transitions to closed; writes close log with `trigger_reason="api_key_update"`; evicts old key entry from dict. Called by the `update_api_key` MCP tool handler after successful validation.
- [ ] T027 Wire `close_on_key_update` into the `update_api_key` handler in [src/mcp_server/tools.py](src/mcp_server/tools.py) (or wherever the MCP tool's success path runs): after `participant_repo.reset_ai_credentials()` succeeds, call `breaker.close_on_key_update(session_id, participant_id)` if breaker is available in context.

### US2 tests

- [ ] T028 [P] [tests/test_015_probe_recovery.py](tests/test_015_probe_recovery.py) -- US2 acceptance tests:
  - US2 AS1: exactly one probe per backoff tick -- inject a mock adapter; verify probe fires once on schedule, not once per turn
  - US2 AS2: probe success closes breaker -- mock returns ValidationResult.ok=True; next `is_open()` returns False; close log row present
  - US2 AS3: probe failure keeps open, schedule advances -- mock returns False; breaker stays open; next backoff position increments
  - US2 AS3 (exhausted): at last schedule position, cycle-on-last -- position stays pinned; `schedule_exhausted=True` on first cycle-restart probe log row
  - US2 AS4: api_key_update fast-close -- `close_on_key_update()` closes immediately; close log has `trigger_reason="api_key_update"`; in-flight probe cancelled

---

## Phase 5: User Story 3 -- Operators see which participants are isolated and why (Priority: P3)

**Goal**: All audit rows emitted per spec (US3 AS1-AS4); metrics surface exposes per-participant breaker state (FR-013).

### Metrics surface (FR-013)

- [ ] T029 Add per-session circuit breaker state to the metrics endpoint in [src/web_ui/](src/web_ui/) (or the existing Prometheus counter module): expose `sacp_circuit_breaker_open_total`, `sacp_circuit_breaker_open_since`, `sacp_circuit_breaker_trigger_reason` per FR-013. Read from in-memory `CircuitState` dict (current state) not from DB (avoids extra round-trip per metrics scrape).

### US3 tests

- [ ] T030 [P] [tests/test_015_audit_metrics.py](tests/test_015_audit_metrics.py) -- US3 acceptance tests:
  - US3 AS1: trip emits `provider_circuit_open_log` row with all required fields
  - US3 AS2: metrics surface exposes open-breaker count, open-since timestamp, trigger-reason breakdown (SC-004)
  - US3 AS3: close emits `provider_circuit_close_log` row with `total_open_seconds`, `probes_attempted`, `probes_succeeded`
  - US3 AS4: each probe emits `provider_circuit_probe_log` row (success + failure variants)

---

## Polish

- [ ] T031 FR-011 startup check implementation: at `initialize_adapter()` time (or at `CircuitBreaker` construction), inspect the LiteLLM adapter config for ordered-fallback entries; if any entry belongs to a different participant identity (cross-identity), call `raise SystemExit(...)` with a message naming the offending config. The check runs before port binding.
- [ ] T032 [P] FR-017 integration with convergence engine: confirm `skip_reason='circuit_open'` turns are excluded from spec 004's similarity inputs. Add a test or search spec 004's skip-reason filter to verify `circuit_open` is handled alongside `budget_exceeded`.
- [ ] T033 V18 traceability: run `python scripts/check_traceability.py` and confirm all FR-* and SC-* labels in spec.md are referenced by at least one test or source file.
- [ ] T034 Run all seven closeout preflights from repo root and fix any findings:
  - `python scripts/check_traceability.py`
  - `python scripts/check_doc_deliverables.py`
  - `python scripts/check_audit_label_parity.py`
  - `python scripts/check_detection_taxonomy_parity.py`
  - `python scripts/check_schema_mirror.py`
  - `python scripts/check_env_vars.py`
  - `python scripts/check_time_format_parity.py`
