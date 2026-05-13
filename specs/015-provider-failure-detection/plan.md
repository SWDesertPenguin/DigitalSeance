# Implementation Plan: Provider Failure Detection and Isolation (Bridge-Layer Circuit Breaker)

**Branch**: `015-provider-failure-detection` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/015-provider-failure-detection/spec.md`

## Summary

Phase 1 back-fill that replaces the existing 78-line `CircuitBreaker` class (consecutive-failure counter, no audit log, no sliding window, no probe recovery) with a full three-state per-participant circuit breaker. The new implementation is keyed on `(session_id, participant_id, provider, api_key_fingerprint)`, uses a ring-buffer sliding-window failure count, transitions through closed / open / half_open states, issues recovery probes on a configurable backoff schedule, audit-logs every state transition into `admin_audit_log`, and exposes aggregate breaker state in the metrics surface. When all four env vars are unset the behavior is byte-identical to the pre-feature baseline (no implicit defaults).

Technical approach: replace `src/orchestrator/circuit_breaker.py` in-place with the full state machine; wire the new keyed check and failure-recording call sites into the existing `loop.py` dispatch path; add four env-var validators and `docs/env-vars.md` sections as the V16 gate; ship one alembic migration (022) adding three audit tables for open/probe/close events; update `tests/conftest.py` to mirror the new tables; add test files per user story.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new runtime dependencies — the circuit breaker is orchestrator-internal; `CanonicalError` categories already defined in `src/api_bridge/adapter.py` + `src/api_bridge/litellm/errors.py`.
**Storage**: PostgreSQL 16. One new alembic migration (022) adds three append-only audit tables: `provider_circuit_open_log`, `provider_circuit_probe_log`, `provider_circuit_close_log`. In-memory `CircuitState` per session — not persisted across restart (session-local model per spec §Assumptions). `tests/conftest.py` schema mirror updated per `feedback_test_schema_mirror`.
**Testing**: pytest with the existing per-test FastAPI fixture. DB-gated tests follow the conftest schema-mirror pattern.
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm).
**Project Type**: Web service (single project; existing `src/` + `tests/` layout).
**Performance Goals**:
- Breaker state lookup per dispatch: O(1) hash lookup — constant time per FR-001 tuple key (V14).
- Failure recording: O(1) amortized ring-buffer append + window trim (V14).
- Probe calls: out-of-band, MUST NOT block turn dispatch for any other participant (V14).
**Constraints**:
- When all four env vars are unset, behavior is byte-identical to the pre-feature baseline (SC-005).
- Invalid env-var values exit at startup with a clear message naming the offending var (SC-006, V16).
- No transparent provider fallback permitted (FR-011, SC-008).
- Constitution §6.10 coding standards: function bodies under 25 lines, 5-arg positional limit.
**Scale/Scope**: Phase 3 ceiling of 5 participants per session; up to 100 failures per window per participant (FR threshold upper bound).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | Circuit state is strictly per-participant (FR-010). No participant's failures affect another's state, even when sharing the same upstream provider. No transparent fallback (FR-011) preserves model-choice sovereignty per §3. |
| **V2 No cross-phase leakage** | PASS | Phase 1 back-fill. No Phase 4 capabilities required. Topology 7 incompatibility flagged explicitly in spec §V12 (no orchestrator dispatch point for MCP-to-MCP). |
| **V3 Security hierarchy** | PASS | Reliability mechanism, not a security trade-off. Auth-error failures (HTTP 401/403) are classified as `auth_error` category and count toward the threshold — correct signal for key rotation. |
| **V4 Facilitator powers bounded** | PASS | No new facilitator-visible controls in v1. Operator visibility is read-only metrics surface (FR-013). Fast-close via `update_api_key` is an existing operator path that gains a side effect, not a new power. |
| **V5 Transparency** | PASS | Every state transition (open, probe, close, schedule-exhausted) emits an `admin_audit_log` entry (FR-012). Metrics surface exposes per-participant breaker state (FR-013). Skipped turns appear in routing log (FR-017). |
| **V6 Graceful degradation** | PASS | When all env vars are unset, breaker is inactive — current behavior preserved (FR-015, SC-005). Open-breaker turns follow existing §6.6 skip policy (FR-005). 3+ consecutive open-state turns continue to trigger existing auto-pause (FR-005). |
| **V7 Coding standards** | PASS | Ring-buffer and state-machine methods sized to fit under 25-line cap; complex logic split into helper functions with 5-arg positional limit. |
| **V8 Data security** | PASS | `api_key_fingerprint` in the circuit key is a hash/prefix, not the key itself. Audit log rows carry participant_id and session_id only; no API key material in logs. |
| **V9 Log integrity** | PASS | Audit tables are append-only. No UPDATE or DELETE paths on circuit audit rows. |
| **V10 AI security pipeline** | PASS | Circuit breaker operates at the dispatch layer, before any prompt assembly. No change to spec 007 security-pipeline evaluation order. |
| **V11 Supply chain** | PASS | No new runtime dependencies. |
| **V12 Topology compatibility** | PASS | Spec §V12 explicitly enumerates topologies 1-6 as applicable; topology 7 incompatibility documented. |
| **V13 Use case coverage** | PASS | Spec §V13 maps to all four use cases — foundational reliability, not use-case-specific. |
| **V14 Performance budgets** | PASS | Three budgets specified in spec §"Performance Budgets (V14)": O(1) lookup, O(1) amortized record, out-of-band probes. All captured in routing log per stage. |
| **V15 Fail-closed** | PASS | Invalid env-var values exit at startup (V16). When env vars are unset, breaker is inactive (fail-open = preserve baseline). Probe call failure keeps breaker open (conservative). |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Four new env vars require validators + `docs/env-vars.md` sections BEFORE `/speckit.tasks` (FR-014). Validators land as the Phase 2 gate in this spec's task list. |
| **V17 Transcript canonicity respected** | PASS | Short-circuited turns do not write to the messages table. Audit rows go to `admin_audit_log`; routing log entry per spec 003 §FR-030. No transcript mutation. |
| **V18 Derived artifacts traceable** | PASS | No new derived artifact types. Audit rows are primary records, not derived. |
| **V19 Evidence and judgment markers** | PASS | All four NEEDS CLARIFICATION markers resolved Session 2026-05-13. No outstanding markers. |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/015-provider-failure-detection/
+-- plan.md              # This file
+-- research.md          # Phase 0 output
+-- data-model.md        # Phase 1 output
+-- quickstart.md        # Phase 1 output
+-- contracts/
|   +-- circuit-state-machine.md    # Phase 1 output
|   +-- probe-contract.md           # Phase 1 output
+-- checklists/
|   +-- security.md                 # Step 5 output
+-- spec.md              # Feature spec (Status: Clarified, session 2026-05-13)
+-- tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
+-- orchestrator/
|   +-- circuit_breaker.py          # REPLACE 78-line implementation with full state machine
+-- config/
|   +-- validators.py               # add 4 validators (SACP_PROVIDER_FAILURE_THRESHOLD,
|                                   #   SACP_PROVIDER_FAILURE_WINDOW_S,
|                                   #   SACP_PROVIDER_RECOVERY_PROBE_BACKOFF,
|                                   #   SACP_PROVIDER_PROBE_TIMEOUT_S)

alembic/versions/
+-- 022_circuit_breaker_audit.py    # NEW: 3 append-only audit tables

tests/
+-- conftest.py                     # mirror new audit tables in raw DDL
+-- test_015_circuit_breaker.py     # NEW: US1 state machine, trip, short-circuit, isolation
+-- test_015_probe_recovery.py      # NEW: US2 probe schedule, backoff, close-on-success
+-- test_015_audit_metrics.py       # NEW: US3 audit rows, metrics surface, fast-close
+-- test_015_validators.py          # NEW: 4 env-var validators

docs/
+-- env-vars.md                     # add 4 new sections (V16 gate; FR-014)
```

**Structure Decision**: Single Python service (existing `src/` + `tests/` layout). `circuit_breaker.py` is replaced in-place rather than introducing a new module; the existing import in `loop.py` and the existing call sites continue to work through the same module path. The three audit tables ship in a single migration (022) to keep the chain atomic.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations.)

## Phase 0 — Outline & Research

Open decisions queued for `research.md`:

1. **State machine: three-state vs two-state.** `open` / `closed` only vs. `open` / `half_open` / `closed`. Two-state is simpler: a probe success transitions directly from open to closed. Three-state makes the probing period explicit — during `half_open` the breaker admits exactly one dispatch (the probe) and transitions on outcome. Decision criteria: clarity of the probe contract, spec FR-006 "at most one probe per backoff tick" semantics, interaction with US3 metrics visibility (operators see `half_open` as a distinct observable state).
2. **Ring-buffer implementation.** In-process Python list with index rotation vs. `collections.deque(maxlen=N)` vs. time-bucketed counters. Decision criteria: memory bound, trim-on-read vs. trim-on-write semantics, interaction with sliding-window correctness (old entries outside the window must not count).
3. **Probe design.** Full LiteLLM dispatch call vs. `adapter.validate_credentials()`. Decision criteria: FR-007 requires a minimal-cost call that does not enter the transcript; `validate_credentials()` already exists in the `ProviderAdapter` ABC and is the same call used by `update_api_key`. Choosing `validate_credentials` avoids synthesizing a fake message list.
4. **Backoff schedule parsing.** Comma-separated string `SACP_PROVIDER_RECOVERY_PROBE_BACKOFF`. Parse at startup vs. parse at first use. Cycle-on-last-value semantics when the schedule is exhausted. Each entry validated as int in `[1, 600]` at startup, not at probe time.
5. **Integration with loop.py.** Two call sites: (a) before dispatch — `is_open()` check in `_check_skip_conditions()`; (b) after a dispatch failure — `record_failure()` in `_record_failure_and_announce()`. The existing call signatures pass only `participant_id`; the new keyed signature needs `(session_id, participant_id, provider, api_key_fingerprint)`. Research §5 decides how `provider` and `api_key_fingerprint` are threaded through without widening the existing loop call stack excessively.
6. **V16 deliverable.** Four env vars, their validators, defaults-mean-inactive semantics, paired validation (threshold + window must both be set or both unset).

Output: [research.md](./research.md) with one decision section per open question.

## Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **Data model** ([data-model.md](./data-model.md)) — entities from spec:
   - `CircuitState` in-memory dataclass (session-local, per FR-001 key tuple).
   - `FailureRecord` ring buffer (timestamp + failure_kind per entry).
   - `provider_circuit_open_log` audit table schema.
   - `provider_circuit_probe_log` audit table schema.
   - `provider_circuit_close_log` audit table schema.
   - In-memory vs. DB persistence decision (session-local per spec §Assumptions).

2. **Contracts** ([contracts/](./contracts/)) — two contract docs:
   - `contracts/circuit-state-machine.md` — three-state machine (closed / open / half_open): all transitions, their triggers, and guards.
   - `contracts/probe-contract.md` — what a probe call looks like (`validate_credentials()`), how the result is classified (ok / failure), and what happens to the breaker on each outcome.

3. **Quickstart** ([quickstart.md](./quickstart.md)) — operator workflow:
   - Enable the circuit breaker by setting the 4 env vars.
   - Observe breaker state in `admin_audit_log` query.
   - Observe breaker state in metrics surface.
   - Disable / roll back by unsetting all four vars.

4. **Agent context update**: run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType claude` to merge spec 015's tech surface into `CLAUDE.md`.

5. **Re-evaluate Constitution Check** post-design — confirm V14 budgets and V16 surfaces are still accurate after `data-model.md` and `contracts/` lock the schema.

**Output**: data-model.md, contracts/*.md, quickstart.md, updated CLAUDE.md.

## Notes for `/speckit.tasks`

- Task list MUST gate the V16 deliverable (4 validators registered in `VALIDATORS` tuple + `docs/env-vars.md` sections) BEFORE any US-phase code work per FR-014.
- The alembic migration 022 AND `tests/conftest.py` schema-mirror update MUST land together in a single task (memory: `feedback_test_schema_mirror` — CI builds schema from conftest, not migrations).
- Paired-var validation (threshold + window must both be set or both unset) is a cross-validator dependency; the cross-check validator function runs AFTER both individual validators in the `VALIDATORS` tuple ordering.
- `circuit_breaker.py` is a replacement, not an addition. The existing import path `from src.orchestrator.circuit_breaker import CircuitBreaker` must continue to resolve; the new `CircuitBreaker` class signature MAY change (new key parameters) — confirm `loop.py` call sites are updated atomically in the same task as the replacement.
- SC-005 regression test (env vars unset = byte-identical baseline) should land early to catch any unintended default activation.
- SC-008 startup-check test (cross-identity fallback list detected = refuse to start) is a contract test requiring a fake LiteLLM config injection.
- Spec 011 amendment: not needed for this spec (no SPA changes; circuit breaker is operator-side only). No amendment to track.
