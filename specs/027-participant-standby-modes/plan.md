# Implementation Plan: AI Participant Standby Modes (wait_for_human + always)

**Spec**: `specs/027-participant-standby-modes/spec.md`
**Status**: Plan complete 2026-05-12 (full-pass clarify + plan + tasks + implement session).

## Technical Context

- **Language / version**: Python 3.14.4 slim-bookworm (per Constitution §6.8). No version change.
- **Primary dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest — already pinned at the repository root. **No new runtime dependencies.** Frontend remains the UMD + Babel-Standalone pattern from spec 011; no new third-party libraries.
- **Storage**: PostgreSQL 16. One new alembic migration (`021_participant_standby_modes.py`, pre-allocated revision slot per parallel-lane coordination memo). The migration adds three nullable columns to `participants` — `wait_mode TEXT NOT NULL DEFAULT 'wait_for_human'` (CHECK constrained to `wait_for_human` / `always`), `standby_cycle_count INTEGER NOT NULL DEFAULT 0`, `wait_mode_metadata JSONB NOT NULL DEFAULT '{}'::jsonb` — plus a partial index on `(session_id, status) WHERE status = 'standby'` to keep round-robin skip-set arithmetic O(1) regardless of session size.
- **Project type**: Backend orchestrator extension (single-process Python service) + frontend SPA additions (spec 011 amendments FR-052..FR-059).

## Constitution Check (V1..V20)

- **V1 Sovereignty**: Standby state is auto-managed by the orchestrator; no participant's API key, model choice, prompt content, or routing-mode is touched. The `wait_mode` is participant-facing configuration — the human owning the AI chooses it. The `always`-mode acknowledgment delta is a Tier 4 fragment, not a hidden instruction; the human sees it in the assembled prompt via spec 010's debug-export. PASS.
- **V2 No cross-phase leakage**: All capabilities are Phase-3-declared. PASS.
- **V3 Security hierarchy**: Pivot text is hardcoded and pre-validated through spec 007's security pipeline at module import (FR-022). No untrusted-input path. PASS.
- **V4 Facilitator bounds**: The FR-025 `wait_mode` setter is participant-side (the participant's owning human, or the facilitator acting on behalf — same surface as existing participant settings per spec 002). Facilitator powers gain one new audit action (`wait_mode_changed`) — additive only. PASS.
- **V5 Transparency**: Every standby entry / exit / pivot writes an `admin_audit_log` row + emits a WS event. PASS.
- **V6 Graceful degradation**: Failure modes are bounded — the standby evaluator failing for a participant skips standby evaluation that tick (logged as `standby_eval_error` in `routing_log`); the participant continues to round-robin per pre-feature behavior. No halt path. PASS.
- **V7 Coding standards**: 25/5 limits respected throughout; all signatures type-hinted; caller-above-callee. PASS — verified at PR diff review time.
- **V8 Data security**: The three new participant columns carry no secrets, no sensitive metadata. The `wait_mode_metadata` JSONB is bounded to documented keys (`long_term_observer` boolean in v1). PASS.
- **V9 Log integrity**: Standby state changes write to `admin_audit_log` (append-only); the `standby_cycle_count` is an UPDATE on `participants` (not a log table), permitted under the existing application DB role. PASS.
- **V10 AI security pipeline**: The acknowledgment delta is Tier 4 (system-trust). The pivot message is `speaker_type='system'` (system-trust). Neither path introduces untrusted content. PASS.
- **V11 Supply chain**: No new dependencies. PASS.
- **V12 Topology compatibility**: Applies to topologies 1-6. Incompatible with topology 7 (orchestrator is not the dispatch authority there). Documented in §V12 Topology Applicability of `spec.md`. PASS.
- **V13 Use case coverage**: Research co-authorship (§2), consulting (§3), asymmetric expertise (§6) — documented in §V13 of `spec.md`. PASS.
- **V14 Performance budgets**: Three budgets documented (Performance Budgets section): standby evaluator O(1) per participant per tick (P95 < 1ms), pivot injection P95 < 100ms, state transition P95 < 50ms. Instrumented via the existing `routing_log` per-stage timing path (spec 003 §FR-030). PASS.
- **V15 Security pipeline fail-closed**: The pivot text passes through `src/security/output_validator.py` at module-import time (FR-022). If validation fails at import, the module raises `ImportError` — the orchestrator refuses to start. PASS.
- **V16 Configuration**: Four new env vars (`SACP_STANDBY_DEFAULT_WAIT_MODE`, `SACP_STANDBY_FILLER_DETECTION_TURNS`, `SACP_STANDBY_PIVOT_TIMEOUT_SECONDS`, `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION`) with validators in `src/config/validators.py` and entries in `docs/env-vars.md`. PASS.
- **V17 Transcript canonicity**: The pivot message is appended (INSERT) to the `messages` table — not a rewrite. No mutation of prior turns. PASS.
- **V18 Derived artifacts**: No derived artifacts introduced. PASS.
- **V19 Evidence and judgment**: The Phase 1+2 shakedown observation is paraphrased per Session 2026-05-12 Q9. PASS.

## Implementation Phases

The work splits into four phases that mirror the user-story priorities in `spec.md`:

### Phase 1 — Schema + status enum + participant model (P1 foundation)

Lands the alembic migration `021_participant_standby_modes.py`, the `tests/conftest.py` raw-DDL mirror, and the `Participant` dataclass extensions. Adds the four V16 env-var validators + their `docs/env-vars.md` sections. No behavior change yet; the columns exist and default to safe values. Independent test target: `tests/test_027_validators.py` + `tests/test_027_architectural.py`.

### Phase 2 — Standby evaluator + round-robin skip + WS events (P1 critical path)

Implements `src/orchestrator/standby.py` (the evaluator), wires it into the round-robin tick path in `src/orchestrator/loop.py`, registers the new WS event types (`participant_standby`, `participant_standby_exited`), and adds the new audit action labels (`standby_entered`, `standby_exited`, `wait_mode_changed`) to both `audit_labels.py` mirrors. Independent test target: `tests/test_027_standby_evaluator.py`, `tests/test_027_loop_integration.py`, `tests/test_027_ws_events.py`. Acceptance scenarios US1.1..US1.7 covered.

### Phase 3 — `always`-mode Tier 4 delta + composition (P2)

Implements `src/prompts/standby_ack_delta.py` (hardcoded text, pre-validated through `src/security/output_validator.py`) and wires it into `src/prompts/tiers.py:assemble_prompt` after the spec 025 conclude delta and after the spec 021 register-slider delta (fixed-additive-order per Session 2026-05-12 Q5). Independent test target: `tests/test_027_always_mode_delta.py`, `tests/test_027_delta_composition.py`. Acceptance scenarios US2.1..US2.5 covered.

### Phase 4 — Auto-pivot + long-term-observer + rate cap (P3)

Implements the pivot evaluator + injector, the per-session rate cap, the long-term-observer transition, and the new audit actions (`pivot_injected`, `standby_observer_marked`). Independent test target: `tests/test_027_pivot_mechanism.py`, `tests/test_027_long_term_observer.py`. Acceptance scenarios US3.1..US3.5 covered.

### Phase 5 — Spec 011 amendments + frontend rendering

Co-drafts the eight spec 011 amendments (FR-052..FR-059) in `specs/011-web-ui/spec.md`. Implements the participant-card badge + pill + long-term-observer variant + facilitator toggle in `frontend/app.jsx`. The pure-logic helpers live in `frontend/standby_ui.js` (UMD + Node-test pattern per the established `frontend_polish_module_pattern` memory). Independent test target: `tests/frontend/test_standby_ui.js`.

### Phase 6 — E2E + closeout

End-to-end test `tests/e2e/test_027_standby_e2e.py` (skip-gated by `SACP_RUN_E2E=1`). Audit-label parity gate, detection-taxonomy parity gate (no change for this spec), traceability + migration-chain + doc-deliverables preflights all green. Spec status flips to Implemented 2026-05-12.

## Performance Budgets (V14)

Per `spec.md` Performance Budgets section:

- **Standby evaluator per participant per tick**: O(1). The four detection signals each resolve to a constant-time lookup against an in-memory unresolved-gates set (the loop already maintains these for round-robin skip). P95 < 1ms per participant. Captured in `routing_log.standby_eval_ms`.
- **Pivot injection**: O(1). One `admin_audit_log` write + one `messages` INSERT + one WS broadcast. Rate-capped at `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION` per session. P95 < 100ms. Captured in `routing_log.pivot_inject_ms`.
- **Standby state transition**: O(1). One `participants` UPDATE + one `admin_audit_log` INSERT + one WS broadcast. P95 < 50ms. Captured in `routing_log.standby_transition_ms`.

Regression detection: the existing `tests/test_003_perf_regression.py` framework gets a new function `test_standby_evaluator_perf_p95` that drives a 100-tick session and asserts the P95 < 1ms budget against the recorded `routing_log` rows.

## Tests Strategy

- **Unit**: `tests/test_027_standby_evaluator.py` covers the four detection signals individually; `tests/test_027_validators.py` covers the V16 validators; `tests/test_027_pivot_mechanism.py` covers the pivot rate cap, the long-term-observer transition, and the rate-cap-exhausted skip path; `tests/test_027_always_mode_delta.py` covers the `always`-mode Tier 4 delta presence + composition.
- **Integration**: `tests/test_027_loop_integration.py` drives a multi-tick session asserting the evaluator + skip-set + WS event chain.
- **Architectural**: `tests/test_027_architectural.py` asserts the new audit-action labels are registered in both `audit_labels.py` mirrors; the new env vars are registered in `VALIDATORS` tuple; the migration `021_*` is the head; the `participants` raw DDL in `tests/conftest.py` carries the three new columns.
- **E2E**: `tests/e2e/test_027_standby_e2e.py` skip-gated by `SACP_RUN_E2E=1`; covers the full P1+P2+P3 paths end-to-end through the FastAPI + WebSocket surface.
- **Regression**: `tests/test_027_regression_pre_feature.py` asserts that with `SACP_STANDBY_DEFAULT_WAIT_MODE=always` set session-wide, the pre-feature serialized turn loop behavior is byte-identical (SC-001 inverse — no standby fires).

## Acceptance Gates

- All four V16 validators land in `src/config/validators.py` AND are registered in the `VALIDATORS` tuple AND have entries in `docs/env-vars.md` BEFORE tasks.md is run (V16 deliverable gate).
- The migration `021_*` chain-links to `018_compression_log.py` (current head) per the parallel-lane coordination memo (lane A uses `019_*`, lane B may use `020_*`, this lane is `021_*`).
- The five new audit-action labels are registered in both `src/orchestrator/audit_labels.py` AND `frontend/audit_labels.js` (CI parity gate).
- The three new participant columns are mirrored in `tests/conftest.py` raw DDL per `feedback_test_schema_mirror`.

## Out of Scope

- Per-participant pivot rate-capping (FR-019 caps per-session in v1; per-participant is a future amendment).
- Operator-tunable detection signal #3 thresholds (FR-006 hardcodes the values per Session 2026-05-12 Q8; future amendment if false-positive rate is high).
- Operator-configurable Tier 4 delta order (Session 2026-05-12 Q5 fixed the order).
- Topology 7 (MCP-to-MCP) — orchestrator is not the dispatch authority there.
