# Implementation Plan: High-Traffic Session Mode (Broadcast Mode)

**Branch**: `013-high-traffic-mode` | **Date**: 2026-05-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-high-traffic-mode/spec.md`

## Summary

Phase 3 broadcast mode delivered via three orthogonal mechanisms layered onto the Phase 2 orchestrator: (1) human-boundary message batching cadence, (2) per-session convergence-threshold override, (3) participant observer-downgrade on traffic spikes. Each mechanism is independently env-var-gated, fail-closes to current Phase 2 behavior when disabled, and instruments per-stage timings into `routing_log` per spec 003 §FR-030. Three new `SACP_*` env vars + V16 validators land before `/speckit.tasks`.

Technical approach: extend `src/orchestrator/loop.py` with a `HighTrafficSessionConfig` resolved at session-start; route AI-to-human messages through a new `BatchEnvelope` queue in `src/web_ui/events.py` keyed by recipient + session; thread the convergence override through `src/orchestrator/convergence.py` `_threshold` initialization; add an `observer-downgrade` evaluator to `src/orchestrator/loop.py`'s turn-prep phase that reads existing `participant.role` / `model_tier` / `consecutive_timeouts` to pick the lowest-priority active participant.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new runtime dependencies.
**Storage**: PostgreSQL 16. Three new event types reuse the existing `admin_audit_log` table — no schema change, no new migration (decision in [research.md §1](./research.md)).
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). DB-gated tests follow the `tests/conftest.py` schema-mirror pattern. Phase 2 acceptance scenarios MUST pass unmodified when all three env vars are unset (SC-005 regression contract).
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). No client-side work — Web UI absorbs the new batch-envelope event without new component code (event format is additive).
**Project Type**: Web service (single project, existing layout — `src/` + `tests/`).
**Performance Goals**:
- Batching latency P95 ≤ `cadence + 5s` scheduling slack (SC-002).
- Convergence-override read O(1) constant-time field access, no per-turn env-var lookup observable in `routing_log` (SC-003).
- Observer-downgrade evaluation O(participants), within existing turn-prep budget at participant counts up to 5 (SC-004).
**Constraints**:
- All three mechanisms additive — must NOT alter dispatch path semantics in topologies 1–6 when the relevant env var is unset (FR-015).
- V15 fail-closed: regex/parse errors during config resolution exit at startup, never silent fallback to global defaults (FR-007 explicit).
- 25/5 coding standards (Constitution §6.10) + 25-line function cap.
**Scale/Scope**: Phase 3 ceiling of 5 participants per session. Threshold defaults assume this ceiling. Cross-session isolation is unchanged (per-session config object lifetime = session lifetime).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | No change to API key isolation, model choice, budget autonomy, or exit freedom. |
| **V2 No cross-phase leakage** | PASS | Spec is gated on Phase 3 declaration per Constitution §10. No Phase 4 capabilities required. |
| **V3 Security hierarchy** | PASS | No security/correctness trade-off; all three mechanisms preserve existing security pipeline behavior. |
| **V4 Facilitator powers bounded** | PASS | New env vars are operator/deployment surfaces, not facilitator runtime tools. Audit events visible in admin_audit_log. |
| **V5 Transparency** | PASS | All three mechanisms emit audit events (`observer_downgrade`, `observer_restore`, `observer_downgrade_suppressed`). Batch envelopes carry source turn IDs for traceability. |
| **V6 Graceful degradation** | PASS | Each mechanism fail-closes to its Phase 2 behavior when env vars are unset. Invalid config exits at startup (V16); no silent runtime degradation. |
| **V7 Coding standards** | PASS | Function bodies stay under 25 lines; new helpers respect 5-arg positional limit. |
| **V8 Data security** | PASS | No new secrets, no change to data tier classifications. Batch envelopes contain message references only (source turn IDs), no new content. |
| **V9 Log integrity** | PASS | Audit events use the existing append-only path. New audit shape (if added) follows admin_audit_log INSERT-only constraint. |
| **V10 AI security pipeline** | PASS | Mechanisms operate ON the dispatch path but do not bypass any pipeline layer. Validation runs before any batched message is queued; pipeline output flows into the batch envelope unchanged. |
| **V11 Supply chain** | PASS | No new dependencies. |
| **V12 Topology compatibility** | PASS | Spec §V12 explicitly enumerates topology 1–6 applicability; topology 7 incompatibility flagged. |
| **V13 Use case coverage** | PASS | Spec §V13 maps mechanisms to use cases §3 (Consulting) and §2 (Research Co-authorship). |
| **V14 Performance budgets** | PASS | Three budgets specified in spec §"Performance Budgets (V14)" with `routing_log` instrumentation hooks. |
| **V15 Fail-closed** | PASS | Each mechanism has explicit fail-closed semantics on unset/invalid config (FR-013). |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Three new env vars require validators + doc sections BEFORE `/speckit.tasks` (FR-014). Validators land in this feature's task list. |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/013-high-traffic-mode/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (audit event schemas, batch envelope shape)
├── checklists/          # Spec-time checklists (already present)
├── spec.md              # Feature spec
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created here)
```

### Source Code (repository root)

```text
src/
├── orchestrator/
│   ├── loop.py                  # extend turn-prep with downgrade evaluator (mechanism 3)
│   ├── convergence.py           # accept per-session threshold override (mechanism 2)
│   ├── high_traffic.py          # NEW — HighTrafficSessionConfig dataclass + resolution
│   └── observer_downgrade.py    # NEW — priority computation + downgrade decision
├── web_ui/
│   ├── events.py                # extend with BatchEnvelope event + flush scheduler
│   └── batch_scheduler.py       # NEW — per-session per-recipient batch close-time loop
├── config/
│   └── validators.py            # add 3 validators for the new SACP_* env vars
├── repositories/
│   └── session_repo.py          # surface high-traffic config alongside session row (read path)
└── operations/                  # (existing — no work expected here)

tests/
├── test_013_batching.py         # NEW — mechanism 1 acceptance scenarios (US1)
├── test_013_convergence_override.py  # NEW — mechanism 2 (US2)
├── test_013_observer_downgrade.py    # NEW — mechanism 3 (US3) + edge cases
└── test_013_regression_phase2.py     # NEW — SC-005 regression: all env vars unset = identical Phase 2 behavior
```

No new alembic migration: the three new audit-event types reuse the existing `admin_audit_log` table per [research.md §1](./research.md). `tests/conftest.py` schema mirror remains unchanged.

**Structure Decision**: Single Python service ("Option 1") consistent with the existing repo layout. Two new orchestrator submodules (`high_traffic.py`, `observer_downgrade.py`) keep mechanism logic isolated; `loop.py` only gains call-sites, not bodies. Web-UI batching gets its own scheduler module so the loop and the delivery path remain decoupled.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations.)

## Phase 0 — Outline & Research

Open decisions queued for `research.md`:

1. **Audit-event storage shape**. Add new event types to existing `admin_audit_log`, OR new `observer_downgrade_log` table? Spec assumption is "no schema changes needed if taxonomy already supports it" — research validates this against current `admin_audit_log` structure (event_type + JSON payload).
2. **`SACP_OBSERVER_DOWNGRADE_THRESHOLDS` parse format**. Spec proposes `participants:4,tpm:30` comma-separated; research compares against alternatives (JSON env, prefix-per-key like `SACP_OBSERVER_DOWNGRADE_PARTICIPANTS=4` + `_TPM=30`). Decision criteria: validator complexity, operator-typo blast radius, V16 fail-closed clarity.
3. **"Lowest-priority active participant"** heuristic. Candidates: lowest `model_tier` → most recent `consecutive_timeouts` > 0 → most recent join. Research grounds this in existing routing/circuit-breaker fields and pins the decision before implementation.
4. **Batching transport**. Web UI delivery currently flows via `broadcast_to_session` (websocket). Decision: per-recipient envelope assembled in-process and emitted as a single websocket event, OR per-recipient queue with per-recipient flush task. Research informs the right granularity given that humans are typed (`role IN ('facilitator', 'participant')` with non-AI provider).
5. **Convergence-override resolution timing**. Confirm spec 004's convergence engine has a session-init injection point (spec assumption line 472–474). If not, research scopes the minimal refactor — likely passing the override into `ConvergenceEngine.__init__` from the loop's session-start path.
6. **Phase 2 regression contract enforcement**. SC-005 requires all Phase 2 acceptance scenarios pass unmodified with the env vars unset. Research lists which Phase 2 tests already cover the dispatch path and confirms the feature flag's "additive when unset" guarantee is structurally enforceable (single conditional read at the relevant call sites).

Output: [research.md](./research.md) with one decision section per open question.

## Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **Data model** ([data-model.md](./data-model.md)) extracts entities from spec:
   - `HighTrafficSessionConfig` (frozen dataclass; in-memory only; lifetime = session) — fields: `batch_cadence_s: int | None`, `convergence_threshold_override: float | None`, `observer_downgrade_thresholds: ObserverDowngradeThresholds | None`.
   - `ObserverDowngradeThresholds` — fields: `participants: int`, `tpm: int`, `restore_window_s: int` (sustained drop window before re-enabling a downgraded participant).
   - `BatchEnvelope` — fields: `recipient_id`, `source_turn_ids: list[str]`, `opened_at: datetime`, `scheduled_close_at: datetime`, `messages: list[ContextMessage]`.
   - `ObserverDowngradeRecord` — fields: `session_id`, `participant_id`, `downgrade_at`, `restore_at: datetime | None`, `trigger_threshold: str` (which threshold tripped), `trigger_value: str` (the observed value vs configured).
   - `DowngradeSuppressedRecord` — same shape minus `restore_at`.

2. **Contracts** ([contracts/](./contracts/)) — Phase 1 outputs three contract docs:
   - `contracts/audit-events.md` — event_type strings, payload shape, persistence rules, cross-ref to admin_audit_log schema.
   - `contracts/batch-envelope.md` — websocket event shape (envelope wraps multiple existing message events; bypass rule for convergence/state-change events).
   - `contracts/env-vars.md` — three new vars with the six standard fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec).

3. **Quickstart** ([quickstart.md](./quickstart.md)) — operator workflow:
   - Set env var(s), restart orchestrator, verify config-validation passes.
   - Trigger conditions for each mechanism (bash invocation that drives traffic above threshold).
   - How to read `routing_log` for batching open/close times and downgrade evaluation costs.
   - Disabling/rollback (unset env var, restart).

4. **Agent context update**: run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType claude` to merge Phase 3 technologies into `CLAUDE.md`.

5. **Re-evaluate Constitution Check** post-design — confirm no V14/V15/V16 surfaces shifted.

**Output**: data-model.md, contracts/*.md, quickstart.md, updated CLAUDE.md.

## Notes for `/speckit.tasks`

- Task list MUST gate validator+doc work (FR-014) BEFORE any code-path work.
- Each mechanism's tests can land independently — the spec's orthogonality holds at the test level.
- Phase 2 regression suite (SC-005) is a single new test file that re-runs targeted Phase 2 acceptance scenarios with all three env vars unset — `tasks.md` should land it as the FIRST task after env-var validators (early canary if any mechanism's "additive when unset" guarantee leaks).
- Audit-event taxonomy is in scope for `tasks.md`; the shape is locked by `contracts/audit-events.md`.
