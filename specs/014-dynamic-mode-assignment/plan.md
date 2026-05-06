# Implementation Plan: Dynamic Mode Assignment (Signal-Driven Controller for High-Traffic Mode)

**Branch**: `014-dynamic-mode-assignment` | **Date**: 2026-05-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/014-dynamic-mode-assignment/spec.md`

## Summary

Phase 3 dynamic controller layered above spec 013's high-traffic mechanisms. Observes a rolling 5-minute window of four session signals (turn rate, convergence derivative, queue depth, density anomaly rate); decides at a rate-capped cadence whether to ENGAGE or DISENGAGE high-traffic mode; either emits advisory recommendations (default) or auto-applies transitions behind a feature flag (`SACP_AUTO_MODE_ENABLED`). Hysteresis dwell time bounds flap; ENGAGE/DISENGAGE asymmetry biases toward engagement. Six new `SACP_DMA_*` env vars + V16 validators land before `/speckit.tasks`.

Technical approach: new `src/orchestrator/dma_controller.py` runs as a per-session asyncio task with a bounded ring buffer; reads existing signal sources (turn rate from loop, similarity from `convergence.py`, queue depth from spec-013 batching, density-anomaly rate from `density.py`); writes mode_* audit events to `admin_audit_log`; gates auto-apply on `SACP_AUTO_MODE_ENABLED` and dwell-floor timestamps; toggles spec-013 mechanisms via the per-session `HighTrafficSessionConfig` (mutable in this controller's auto-apply path, immutable elsewhere).

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new runtime dependencies.
**Storage**: PostgreSQL 16. Five new event types reuse the existing `admin_audit_log` table (no schema change; same pattern as 013).
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). DB-gated tests follow the schema-mirror pattern. Spec-013-only baseline (`SACP_DMA_*` all unset) MUST pass unmodified (SC-004 regression contract).
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). No client-side work — recommendations land in audit log only; no Web UI surface in initial Phase 3 delivery.
**Project Type**: Web service (single project, existing layout — `src/` + `tests/`).
**Performance Goals**:
- Per-decision-cycle controller cost ≤ 50ms P95 at 5 participants × all 4 signals (SC-003).
- Decision cap at 12 decisions/min initial (one tick / 5 seconds); excess decisions dropped, not queued (FR-002).
- Hysteresis dwell prevents flap; transition cost is bounded by spec-013 mechanism activation cost (which has its own V14 budgets).
**Constraints**:
- Additive — no behavior change with all `SACP_DMA_*` unset (FR-015 + SC-004).
- Spec 014 cannot reconfigure spec-013 mechanisms beyond toggling on/off (FR-016).
- V15 fail-closed: invalid env vars exit at startup; `SACP_AUTO_MODE_ENABLED=true` without `SACP_DMA_DWELL_TIME_S` exits (FR-010).
- 25/5 coding standards (Constitution §6.10).
**Scale/Scope**: Phase 3 ceiling 5 participants. One controller task per session. Window depth = 5 minutes / decision-cycle interval = ~60 entries per signal source at the initial 12 dpm cap.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | No change to API key isolation, model choice, budget autonomy. Controller decisions never alter participant configuration. |
| **V2 No cross-phase leakage** | PASS | Phase 3 deliverable, gated on facilitator declaration AND spec 013 reaching Implemented. |
| **V3 Security hierarchy** | PASS | Controller never alters security pipeline; pure decision/recommendation layer. |
| **V4 Facilitator powers bounded** | PASS | `SACP_DMA_*` and `SACP_AUTO_MODE_ENABLED` are operator/deployment surfaces, not facilitator runtime tools. |
| **V5 Transparency** | PASS | All decisions emit `mode_recommendation` audit events; auto-apply transitions emit `mode_transition` (or `mode_transition_suppressed` when dwell blocks). Throttled cycles emit `decision_cycle_throttled`. |
| **V6 Graceful degradation** | PASS | Controller fail-closes to inactive when unconfigured. Signal-source unavailability yields rate-limited audit events, not errors (FR-013). |
| **V7 Coding standards** | PASS | Function bodies under 25 lines; helpers respect 5-arg positional limit. |
| **V8 Data security** | PASS | No new secrets, no new data tier classification. Audit rows contain decision metadata only, not message content. |
| **V9 Log integrity** | PASS | All audit events go through the existing append-only path. |
| **V10 AI security pipeline** | PASS | Controller does not touch dispatch path; toggles spec-013 mechanisms whose security properties are already validated. |
| **V11 Supply chain** | PASS | No new dependencies. |
| **V12 Topology compatibility** | PASS | Spec §V12 applies to topologies 1–6; topology 7 incompatibility flagged (matches spec 013). |
| **V13 Use case coverage** | PASS | Spec §V13 maps to use cases §3 (Consulting), §2 (Research Co-authorship), §5 (Technical Review/Audit). |
| **V14 Performance budgets** | PASS | Three V14 budgets in spec §"Performance Budgets" (window cost, decision cap, dwell hysteresis) with `routing_log` instrumentation. |
| **V15 Fail-closed** | PASS | Invalid env vars exit at startup; auto-apply without dwell exits at startup; signal-source unavailability is bounded. |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Six new env vars require validators + doc sections BEFORE `/speckit.tasks` (FR-014). |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/014-dynamic-mode-assignment/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (audit events, signal-source interface, env-vars)
├── spec.md              # Feature spec
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created here)
```

### Source Code (repository root)

```text
src/
├── orchestrator/
│   ├── dma_controller.py        # NEW — per-session controller task; ring buffer; decision loop
│   ├── dma_signals.py           # NEW — signal-source adapters (turn rate, convergence-derivative,
│   │                            #       queue depth, density anomaly); each independently disable-able
│   ├── high_traffic.py          # (from 013) — extend HighTrafficSessionConfig with controller-toggled
│   │                            #              mutability path for auto-apply
│   ├── convergence.py           # (from spec 004) — expose similarity_score on the engine for derivative
│   │                            #                   computation (minimal hook; see research.md §2)
│   └── density.py               # (existing) — read-only signal source; no changes expected
├── config/
│   └── validators.py            # add 6 validators for the new SACP_DMA_* env vars
└── repositories/
    └── log_repo.py              # extend with mode_* audit-event helper if shape benefits from one

tests/
├── test_014_advisory_mode.py        # NEW — US1 (P1) — recommendation emission + advisory boundaries
├── test_014_auto_apply.py           # NEW — US2 (P2) — transition mechanics + dwell hysteresis
├── test_014_signal_independence.py  # NEW — US3 (P3) — per-signal-source isolation
├── test_014_throttle_and_unavailability.py  # NEW — FR-002 cap + FR-013 unavailability rate-limit
├── test_014_regression_spec013_only.py      # NEW — SC-004 regression: spec-013 baseline unchanged
└── conftest.py                     # extend with synthetic-signal fixtures (no real ML inference in tests)
```

**Structure Decision**: Single Python service consistent with existing layout. Two new orchestrator submodules (`dma_controller.py`, `dma_signals.py`) keep controller logic isolated. The signal-source layer is a thin adapter over existing modules — no duplication of measurement code.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations.)

## Phase 0 — Outline & Research

Open decisions queued for `research.md`:

1. **Density-anomaly algorithm**. Spec leaves the concrete algorithm open; current `src/orchestrator/density.py` already computes a density score and flags anomalies via a session-level rolling baseline. Research evaluates whether the existing density flag is sufficient as the controller's signal source, OR whether a higher-cardinality "shifts per window" derivative is needed. Decision criterion: does the existing flag alone discriminate the technical-review use case (§5)?
2. **Spec 004 similarity-score exposure**. The convergence engine computes similarity per turn (line 177 of `convergence.py`). The controller needs read access to compute the per-window derivative. Research scopes the minimal hook: dedicated property, callback, or read from `convergence_log`. Decision criterion: minimize coupling and avoid extra DB reads on the hot path.
3. **Controller task lifecycle**. Per-session asyncio task vs centralized loop polling all sessions? Phase 3 ceiling is 5 sessions × 5 participants typical, so per-session task overhead is acceptable. Research confirms the per-session model integrates cleanly with the existing session-init/teardown path in `loop.py`.
4. **Auto-apply mutation safety on `HighTrafficSessionConfig`**. Spec 013 designed this as in-memory immutable per-session. Spec 014's auto-apply path needs to toggle mechanisms within a session lifetime. Research designs the mutation interface (likely a controller-only `engage_mechanism(name)` / `disengage_mechanism(name)` method on the config object, audited via `mode_transition` events) without breaking spec-013's "additive when unset" guarantee.
5. **Decision-cycle throttle implementation**. FR-002 caps decisions per minute, drops excess, emits `decision_cycle_throttled` (rate-limited per FR-013). Research selects between a token bucket (clean cap semantics, easy to test) and a wall-clock interval check (simpler, but harder to express "12/min" as anything other than "5s between"). Token bucket recommended; finalize.
6. **Recommendation deduplication**. FR-005 says "emit when the decision differs from the most-recently-emitted recommendation". Research clarifies: same trigger signal but different observed values (e.g., turn rate 42 → 45 → 42 over three cycles, all above threshold) — does each one emit, or just the first ENGAGE? Decision: emit only on action change (NORMAL→ENGAGE or ENGAGE→DISENGAGE), not on observed-value changes within the same action.
7. **Topology-7 future-proofing**. Spec is incompatible with topology 7 per V12. Research drafts the explicit-disable check the controller MUST perform if topology 7 ever ships (likely an env-var gate `SACP_TOPOLOGY=7` skips controller initialization entirely).

Output: [research.md](./research.md) with one decision section per open question.

## Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **Data model** ([data-model.md](./data-model.md)) extracts entities from spec:
   - `SessionSignals` (in-memory ring buffer; `O(window_entries)` cost per cycle).
   - `ModeRecommendation` — controller decision shape (action, triggers[], dwell_floor_at).
   - `ModeTransition` — auto-apply variant (adds engaged_mechanisms[], skipped_mechanisms[]).
   - `ModeTransitionSuppressed` — dwell-blocked variant.
   - `ControllerState` — per-session controller's current view (last recommendation, last transition, per-signal health flags). Not persisted.

2. **Contracts** ([contracts/](./contracts/)) — Phase 1 outputs three contract docs:
   - `contracts/audit-events.md` — five new `admin_audit_log` action strings (`mode_recommendation`, `mode_transition`, `mode_transition_suppressed`, `decision_cycle_throttled`, `signal_source_unavailable`); payload shapes.
   - `contracts/signal-source-interface.md` — adapter contract for the four signal sources; how each surfaces "value", "available", and per-cycle cost.
   - `contracts/env-vars.md` — six new vars with the six standard fields each (Default, Type, Valid range, Blast radius, Validation rule, Source spec).

3. **Quickstart** ([quickstart.md](./quickstart.md)) — operator workflow:
   - Enable advisory mode (one threshold env var, restart, observe `mode_recommendation` events).
   - Promote to auto-apply (set `SACP_AUTO_MODE_ENABLED=true` + `SACP_DMA_DWELL_TIME_S`, restart).
   - Tune dwell + thresholds based on observed flap.
   - Disable (unset all `SACP_DMA_*`, restart — controller inactive).
   - Audit-log query examples for the five new event types.

4. **Agent context update**: run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType claude` to merge Phase 3 tech into `CLAUDE.md`.

5. **Re-evaluate Constitution Check** post-design — confirm no V14/V15/V16 surfaces shifted.

**Output**: data-model.md, contracts/*.md, quickstart.md, updated CLAUDE.md.

## Notes for `/speckit.tasks`

- Tasks MUST gate validator+doc work (FR-014) BEFORE any code-path work.
- Spec 013 must reach Status: Implemented before this spec's `/speckit.tasks` is run (per spec 014 line 59–60).
- Initial Phase 3 deployment is advisory-mode-only — `SACP_AUTO_MODE_ENABLED` defaults to false. Auto-apply task work can land in the same feature window; activation is a separate operator decision.
- Per-signal-source independence (US3) is a P3 priority — but the signal-source adapter pattern from `dma_signals.py` benefits ALL three priorities. Land the adapter scaffold first, then per-signal implementations gated by their respective env vars.
- The regression test (SC-004) re-runs spec-013's acceptance scenarios with all `SACP_DMA_*` unset; should land EARLY in the task list as a canary for the additive-when-unset guarantee.
