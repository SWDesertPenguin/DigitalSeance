# Implementation Plan: Session-Length Cap with Auto-Conclude Phase

**Branch**: `025-session-length-cap` | **Date**: 2026-05-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/025-session-length-cap/spec.md`

## Summary

Phase 3 opt-in session-length cap delivered as a four-part mechanism layered onto the existing turn loop: (1) a per-session two-dimensional cap (`length_cap_seconds` + `length_cap_turns` with OR semantics) that defaults to none, (2) a new conclude phase in the loop FSM triggered when elapsed crosses `trigger_fraction × cap` on either dimension, (3) a Tier 4 prompt delta injected during conclude phase asking each AI for one wrap-up turn, (4) a final summarizer trigger that fires the existing spec 005 pipeline once after the last conclude turn before the loop transitions to paused. The cap-set endpoint disambiguates `absolute` vs `relative` interpretation when a new value lands below current elapsed (FR-026). Five new `SACP_*` env vars + V16 validators land before `/speckit.tasks`. A spec 011 amendment lands the SPA wiring (cap-config in session-create + session-settings, conclude-phase banner with countdown, interpretation-choice modal).

Technical approach: extend `src/orchestrator/loop.py` with the conclude-phase FSM state and per-dispatch cap-check call site; introduce `src/orchestrator/length_cap.py` for the cap evaluator, the `active_seconds` accumulator update path, and the cap-decrease disambiguation helper; add `src/prompts/conclude_delta.py` with the hardcoded Tier 4 delta text and integrate via the existing tier hook in `src/prompts/tiers.py`; extend `src/orchestrator/cadence.py` with a conclude-phase suspension hook; thread `final_summarizer_trigger` through `src/orchestrator/summarizer.py` to reuse the spec 005 pipeline; expose cap-set + disambiguation through existing session-settings transports (HTTP via `src/web_ui/`, MCP via `src/mcp_server/tools.py`); add the two new WS events in `src/web_ui/events.py`; ship one alembic migration adding five columns to `sessions` (`length_cap_kind`, `length_cap_seconds`, `length_cap_turns`, `conclude_phase_started_at`, `active_seconds_accumulator`).

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new runtime dependencies.
**Storage**: PostgreSQL 16. One new alembic migration adds five nullable columns to `sessions` (decision in [research.md §1](./research.md) — durable accumulator over volatile in-memory).
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). DB-gated tests follow the `tests/conftest.py` schema-mirror pattern; mirror MUST be updated alongside the alembic migration in the same task.
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). Frontend changes ship as a spec 011 amendment, not in this spec's source tree.
**Project Type**: Web service (single project; existing `src/` + `frontend/` + `tests/` layout).
**Performance Goals**:
- Cap-check per dispatch: O(1) — two integer comparisons + one fraction multiplication, captured in `routing_log` per-stage timings (V14, FR-005).
- Conclude-phase transition: O(participants) — one `routing_log` row, conclude delta queued for each active participant's next assembly, one WS broadcast. P95 < 2s at 5 participants.
- Final summarizer trigger: reuses spec 005 pipeline; budget enforcement falls through to spec 005 SC-002.
- `active_seconds` increment: single column UPDATE on phase transitions only (no per-turn writes).
**Constraints**:
- Default behavior MUST be unchanged: `length_cap_kind='none'` = pre-feature loop, no FR-005..FR-014 code path fires (SC-001 architectural test).
- V15 fail-closed: invalid env-var values exit at startup (V16); conclude delta injection failure is treated like any other Tier 4 assembly failure (existing path).
- 25/5 coding standards (Constitution §6.10) + 25-line function cap.
- §4.13 [PROVISIONAL] inter-AI shorthand: the conclude delta is human-readable English, not negotiated shorthand — clears the rule.
**Scale/Scope**: Phase 3 ceiling of 5 participants per session. Default trigger fraction 0.80; preset caps Short (30 min OR 20 turns), Medium (2 hr OR 50 turns), Long (8 hr OR 200 turns).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | Caps are facilitator-side session policy. No change to API key isolation, model choice, budget autonomy, prompt privacy, or exit freedom. Cap visibility is facilitator-only (FR-019). |
| **V2 No cross-phase leakage** | PASS | Phase 3 declared 2026-05-05. No Phase 4 capabilities required; topology 7 incompatibility flagged in spec §V12. |
| **V3 Security hierarchy** | PASS | Caps are correctness/operations, not security. No security trade-off introduced. |
| **V4 Facilitator powers bounded** | PASS | Cap-set is a session-control endpoint mirroring spec 006 §FR-007 authorization (facilitator-only, HTTP 403 for non-facilitators per FR-016). No new admin powers. |
| **V5 Transparency** | PASS | All transitions emit `routing_log` rows: `cap_set` (FR-004), `conclude_phase_entered` (FR-007), `conclude_phase_exited` (FR-013), `auto_pause_on_cap` (FR-012), `manual_stop_during_conclude` (FR-015). WS events broadcast on phase entry/exit (FR-017, FR-018). |
| **V6 Graceful degradation** | PASS | Default `length_cap_kind='none'` preserves pre-feature behavior. Conclude-turn provider error follows skip-and-continue (FR-011, clarified). Summarizer fail-closed reuses spec 005 §FR-007. |
| **V7 Coding standards** | PASS | Function bodies stay under 25 lines; new helpers respect 5-arg positional limit. |
| **V8 Data security** | PASS | No new secrets, no new data tier classifications. New columns are session metadata. |
| **V9 Log integrity** | PASS | All audit events use existing append-only paths (`routing_log`, `admin_audit_log` for cap-set if facilitator-action level). |
| **V10 AI security pipeline** | PASS | Conclude delta is Tier 4 additive content, passed through the same prompt assembler as participant `custom_prompt`. No new bypass; existing tier isolation, spotlighting, sanitization, and output validation continue to apply. |
| **V11 Supply chain** | PASS | No new runtime dependencies. |
| **V12 Topology compatibility** | PASS | Spec §V12 explicitly enumerates topology 1–6 applicability; topology 7 incompatibility flagged. |
| **V13 Use case coverage** | PASS | Spec §V13 maps to use cases §3 Consulting, §2 Research Co-authorship, §5 Technical Review and Audit. |
| **V14 Performance budgets** | PASS | Three budgets specified in spec §"Performance Budgets (V14)" with `routing_log` instrumentation hooks. |
| **V15 Fail-closed** | PASS | Pipeline-internal failures inherit spec 007's fail-closed semantics; cap-evaluation errors fail-closed by leaving the loop in its current phase (no silent transition). |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Five new env vars require validators + `docs/env-vars.md` sections BEFORE `/speckit.tasks` (FR-025). Validators land in this feature's task list. |
| **V17 Transcript canonicity respected** | PASS | Conclude delta is per-participant pre-bridge prompt content (§4.12), not a transcript mutation. Final summarizer writes a derived artifact via the existing spec 005 path; canonical transcript untouched (§4.10). |
| **V18 Derived artifacts traceable** | PASS | Final summarizer reuses spec 005's existing derivation metadata (source range, summarizer model + prompt version, timestamp); no new artifact types introduced. |
| **V19 Evidence and judgment markers** | PASS | Spec uses [JUDGMENT] / drafted-as / [NEEDS CLARIFICATION] markers consistently; clarify session resolved 5 highest-impact markers, deferred 6 lower-impact items with explicit Outstanding labels. |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/025-session-length-cap/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (cap-set endpoint, WS events, routing-log reasons, env-vars)
├── spec.md              # Feature spec (Status: Draft, clarify session 2026-05-07 complete)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created here)
```

### Source Code (repository root)

```text
src/
├── orchestrator/
│   ├── loop.py                    # extend FSM with conclude phase state; cap-check call site per dispatch
│   ├── length_cap.py              # NEW — SessionLengthCap dataclass, cap evaluator, active_seconds accumulator, disambiguation helper
│   ├── cadence.py                 # add conclude-phase suspension hook (delays return to floor during conclude)
│   └── summarizer.py              # add final_summarizer_trigger entry point invoked from conclude-phase exit
├── prompts/
│   ├── tiers.py                   # extend Tier 4 hook to inject conclude delta (additive after custom_prompt and any spec 021 register delta)
│   └── conclude_delta.py          # NEW — hardcoded Tier 4 delta text + injection helper
├── web_ui/
│   ├── events.py                  # add session_concluding + session_concluded WS event emitters
│   └── session_controls.py        # extend session-settings endpoint with cap-set + disambiguation 409 path
├── mcp_server/
│   └── tools.py                   # add cap-set MCP tool variant (mirrors HTTP shape, same disambiguation contract)
├── repositories/
│   └── session_repo.py            # surface length_cap_* columns; helpers for cap-decrease detection + active_seconds updates
├── config/
│   └── validators.py              # add 5 validators (SACP_LENGTH_CAP_DEFAULT_KIND/_SECONDS/_TURNS, SACP_CONCLUDE_PHASE_TRIGGER_FRACTION/_PROMPT_TIER)
└── models/
    └── session.py                 # add length_cap_*, conclude_phase_started_at, active_seconds_accumulator fields

alembic/versions/
└── NNNN_session_length_cap.py     # NEW — adds 5 nullable columns to sessions

tests/
├── conftest.py                    # mirror new sessions columns in raw DDL (memory: feedback_test_schema_mirror)
├── test_025_cap_evaluator.py      # NEW — FR-005/FR-006 OR semantics + trigger fraction
├── test_025_disambiguation.py     # NEW — FR-026 absolute vs relative endpoint flow
├── test_025_conclude_phase.py     # NEW — FR-008..FR-014 conclude FSM, delta injection, cadence suspension
├── test_025_summarizer_trigger.py # NEW — FR-011 final summarizer fires exactly once; skip-and-continue on provider error
├── test_025_manual_stop.py        # NEW — FR-015 manual_stop_during_conclude runs summarizer before stop
├── test_025_active_seconds.py     # NEW — FR-002 active-time accumulator excludes pause time
├── test_025_validators.py         # NEW — 5 env-var validators
└── test_025_regression_no_cap.py  # NEW — SC-001 default behavior unchanged when length_cap_kind='none'

docs/
└── env-vars.md                    # add 5 new sections (V16 gate; FR-025)
```

**Structure Decision**: Single Python service ("Option 1") consistent with the existing repo layout. New orchestrator submodule `length_cap.py` keeps cap evaluation + accumulator logic isolated; `loop.py` only gains call sites and FSM-edge code, not bodies. New prompts submodule `conclude_delta.py` holds the hardcoded delta text so the assembler stays declarative. Cap-set endpoint extends `session_controls.py` rather than introducing a new file, reusing existing authorization scaffolding.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations.)

## Phase 0 — Outline & Research

Open decisions queued for `research.md`:

1. **`active_seconds` accumulator persistence**. In-memory volatile (cheaper, lost on orchestrator restart) vs. durable column on `sessions` (resilient, one UPDATE per phase transition). Decision criteria: orchestrator-restart resilience, atomic update under pause-resume races, V14 budget impact. Spec line 526–533 leaves this open.
2. **Cap-set endpoint shape**. Extend the existing session-settings endpoint (spec 006 §FR-007) with `length_cap_*` fields vs. dedicated `/sessions/{id}/length_cap` resource. Decision criteria: 409 disambiguation ergonomics (FR-026), existing 006 patterns, OpenAPI surface coherence.
3. **Disambiguation transport**. 409 response containing both interpretations + a follow-up commit (idempotent re-POST with explicit `interpretation` field) vs. two-phase probe + confirm vs. inline `interpretation` parameter on first call (skip 409 entirely). Decision criteria: race-condition resilience, audit traceability, frontend complexity.
4. **Tier 4 composition with spec 021 register slider**. Spec 021 has not shipped. Document the attachment ordering contract (register delta first, conclude delta second, both additive at Tier 4) so 021's later landing is forward-compatible without amendment. Confirm `src/prompts/tiers.py` exposes a deterministic ordering hook before either delta needs to attach.
5. **Conclude delta exact text**. Working draft from spec FR-008. Research evaluates concision (token-budget impact) vs. clarity (multiple AI providers must produce a wrap-up on first read). Settle on a single English sentence + a second sentence describing the orchestrator behavior, ~40 tokens.
6. **Spec 011 amendment scope**. Enumerate the SPA pieces this feature implies: (a) cap-config control set in session-create modal, (b) cap-config control set in session-settings panel, (c) conclude-phase banner with countdown driven by `session_concluding` WS event, (d) disambiguation modal triggered by 409 from cap-set. Decide whether the amendment ships as a single 011 spec.md edit or as a separate amendment doc cross-referenced from this plan.
7. **Cap-decrease detection placement**. Endpoint-level (compare `submitted_value` vs `current_elapsed` before commit) vs. service-layer helper in `length_cap.py` (single source of truth). Decision criteria: keeping the rule reusable for the MCP tool variant.

Output: [research.md](./research.md) with one decision section per open question.

## Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **Data model** ([data-model.md](./data-model.md)) extracts entities from spec:
   - `SessionLengthCap` (per-session columns) — five new fields on `sessions`: `length_cap_kind: enum('none','time','turns','both')` default `'none'`, `length_cap_seconds: int | null`, `length_cap_turns: int | null`, `conclude_phase_started_at: timestamp | null`, `active_seconds_accumulator: int | null`.
   - `LoopState` FSM extension — diagram of running ↔ conclude ↔ paused/stopped edges with the five `routing_log.reason` strings labelling each transition.
   - `ActiveLoopAccumulator` semantics — increment rules (running + conclude phases only; pause excluded), durable column update points (phase transitions), restart recovery semantics.
   - `ConcludeDelta` — Tier 4 fragment, hardcoded text + injection ordering vs. custom_prompt + spec 021 register delta.
   - `CapInterpretation` (audit-log field) — `absolute` | `relative` discriminator captured in `routing_log.cap_set` rows.

2. **Contracts** ([contracts/](./contracts/)) — Phase 1 outputs four contract docs:
   - `contracts/cap-set-endpoint.md` — HTTP shape (request body, validation rules per FR-020/FR-021/FR-022, 200 success, 403 non-facilitator, 409 disambiguation, 422 invalid). MCP tool variant cross-referenced.
   - `contracts/ws-events.md` — `session_concluding` (payload: trigger reason, remaining count, remaining seconds) and `session_concluded` (payload: pause reason). Cross-ref to spec 011 banner consumer.
   - `contracts/routing-log-reasons.md` — five new `reason` enum entries with payload schemas: `cap_set` (old/new values + `interpretation`), `conclude_phase_entered`, `conclude_phase_exited`, `auto_pause_on_cap`, `manual_stop_during_conclude`.
   - `contracts/env-vars.md` — five new vars × six standard fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec).

3. **Quickstart** ([quickstart.md](./quickstart.md)) — operator + facilitator workflows:
   - Operator: set `SACP_LENGTH_CAP_DEFAULT_*` env vars, restart orchestrator, verify config-validation passes.
   - Facilitator: create session with Short preset, watch turn-16 conclude phase fire, observe summarizer + auto-pause.
   - Facilitator: mid-session cap-set demonstrating cap-decrease disambiguation (absolute vs relative).
   - How to read `routing_log` for cap-check timings, conclude-phase entry/exit, summarizer fire.
   - Disabling/rollback: `SACP_LENGTH_CAP_DEFAULT_KIND=none` + per-session override to `'none'`.

4. **Agent context update**: run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType claude` to merge spec 025's tech surface into `CLAUDE.md`.

5. **Re-evaluate Constitution Check** post-design — confirm V14 (cap-check + transition budgets) and V16 (5 env vars) surfaces are still accurate after `data-model.md` and `contracts/` lock the column count and endpoint shape.

**Output**: data-model.md, contracts/*.md, quickstart.md, updated CLAUDE.md.

## Notes for `/speckit.tasks`

- Task list MUST gate the V16 deliverable (5 validators in `src/config/validators.py` registered in `VALIDATORS` tuple + `docs/env-vars.md` sections) BEFORE any code-path work per FR-025.
- The alembic migration AND `tests/conftest.py` schema-mirror update MUST land together in a single task (memory: `feedback_test_schema_mirror.md` — CI builds schema from conftest, not migrations; mismatch surfaces only in CI).
- `test_025_regression_no_cap.py` (SC-001) is the early canary — should land first after the migration so any "no-cap path leak" surfaces before the conclude-phase code grows.
- Spec 011 amendment LANDED 2026-05-07 in this spec's branch (bundled). Spec 011 gained `### Session 2026-05-07 (spec 025 length-cap amendment)` Clarifications entry, US13, FR-021..FR-024, SC-007, and a new "Phase 3a — Length-cap UI (ships with spec 025)" Implementation Phases subsection. Tasks for the four UI surfaces (FR-021/022/023/024) are part of THIS spec's `tasks.md`, not a separate `fix/spec-011-cap-banner` PR.
- Conclude delta text (research.md §5) is locked in `tasks.md`; the task that adds `src/prompts/conclude_delta.py` ships with the final wording, not a placeholder.
- §4.13 PROVISIONAL adherence: conclude delta is human-readable English; no inter-AI shorthand. No `§4.13-review` work item required.
