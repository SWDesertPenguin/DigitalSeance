# Implementation Plan: AI Response Shaping (Verbosity Reduction + Register Slider)

**Branch**: `021-ai-response-shaping` | **Date**: 2026-05-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/021-ai-response-shaping/spec.md`

## Summary

Phase 3 generation-side response shaping, two orthogonal dimensions sharing a common bridge-layer hook. (1) A post-output filler scorer evaluates each AI draft on three normalized signals (hedge-to-content ratio, prior-turn restatement via spec 004's precomputed embeddings, boilerplate-closing regex), aggregates them as a weighted sum, and fires up to two tightened-Tier-4-delta retries when the score crosses `SACP_FILLER_THRESHOLD`. (2) A facilitator-controlled session register slider (1-5) plus an optional per-participant override emits one of five hardcoded `RegisterPreset` deltas into the spec 008 Tier 4 hook. The two controls compose; neither depends on the other beyond sharing the prompt assembler. Three new env vars + V16 validators + `docs/env-vars.md` sections land before `/speckit.tasks`.

Technical approach: new `src/orchestrator/shaping.py` holds the per-model `BehavioralProfile` dict (provider-family-keyed) and the pure-function filler scorer. The scorer reuses the in-memory `ConvergenceEngine.last_embedding` (a one-line spec-004 hook) for restatement-overlap cosine similarity — no second sentence-transformers model load. Retry dispatch reuses spec 003's compound-retry budget per FR-006; the hardcoded 2-retry shaping cap and the compound-retry budget apply jointly (whichever fires first wins). New `src/prompts/register_presets.py` holds the frozen 1-5 preset registry and emits its delta into the spec 008 Tier 4 hook. `SessionRegister` and `ParticipantRegisterOverride` rows persist register state in two new tables wired with spec 001 atomic-delete cascades. The `/me` endpoint extends with three new fields (`register_slider`, `register_preset`, `register_source`).

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new runtime dependencies. Existing sentence-transformers from spec 004 is reused via a `last_embedding` property; no second model load.
**Storage**: PostgreSQL 16. Two new tables (`session_register`, `participant_register_override`); one new alembic migration; `routing_log` extended with five new columns (`shaping_score_ms`, `shaping_retry_dispatch_ms`, `filler_score`, `shaping_retry_delta_text`, `shaping_reason`) — see [data-model.md](./data-model.md) for type/nullability per column. `admin_audit_log` reuses existing schema with three new event types (`session_register_changed`, `participant_register_override_set`, `participant_register_override_cleared`) — no schema change for audit (same pattern as spec 013/014).
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). DB-gated tests follow the schema-mirror pattern (`tests/conftest.py` raw DDL must mirror the new migration; CI builds schema from conftest, not migrations). Pre-feature acceptance tests MUST pass byte-identically with `SACP_RESPONSE_SHAPING_ENABLED=false` (SC-002 regression contract).
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). Server-side only — the register slider's UI surface lands in spec 011 (orchestrator-controls UI) per the spec 011 amendment forward-ref; the `/me` field extension is the only new client-visible surface.
**Project Type**: Web service (single project, existing layout — `src/` + `tests/`).
**Performance Goals**:
- Filler scorer execution per draft: P95 <= 50ms on the hot path (V14 budget 1; spec §"Performance Budgets").
- `RegisterPreset` lookup: O(1) dict access; P95 < 1ms (V14 budget 2).
- Shaping retry dispatch: each retry consumes one full dispatch cycle plus one scorer pass; worst-case shaping overhead per turn is two extra dispatch cycles + three scorer passes, bounded by the hardcoded 2-retry cap (V14 budget 3).
**Constraints**:
- Additive — `SACP_RESPONSE_SHAPING_ENABLED=false` MUST disable the entire scorer + retry pipeline; no behavior change vs. pre-feature baseline (FR-005 + SC-002).
- Slider deltas emit independent of the master switch — register is a prompt-composition concern, not a shaping concern (spec edge case).
- No content compression. The shaping pipeline modifies the *generated* draft before persistence; once persisted, content is immutable per spec 001 §FR-008. Spec 026 owns any work modifying stored content (FR-016).
- 25/5 coding standards (Constitution §6.10).
- V15 fail-closed: invalid env vars exit at startup before binding ports; out-of-range `SACP_FILLER_THRESHOLD`, `SACP_REGISTER_DEFAULT`, or non-parseable `SACP_RESPONSE_SHAPING_ENABLED` exit with a clear error naming the offending value.
**Scale/Scope**: Phase 3 ceiling 5 participants per session. Per-turn dispatch path adds at most three scorer passes (original + 2 retries) bounded by the hardcoded cap. Two new tables remain small (one row per session for register; one row per participant override).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | No change to API key isolation, model choice, budget autonomy. The filler scorer evaluates output text only; register presets emit prompt deltas only. Neither alters participant configuration nor surfaces values across participants. |
| **V2 No cross-phase leakage** | PASS | Phase 3 deliverable, gated on Phase 3 declaration recorded 2026-05-05. No earlier-phase consumer imports any spec-021 surface. |
| **V3 Security hierarchy** | PASS | Tier 4 deltas land at the existing prompt-assembler hook (spec 008 §FR-008); the security pipeline (sanitization, canary placement) is unchanged. The shaping retry never re-runs sanitization on already-clean tier text. |
| **V4 Facilitator powers bounded** | PASS | The session register slider and per-participant override are facilitator runtime tools; both are audit-logged on every change with actor / target / old / new. The three new env vars are operator-deployment surfaces, not facilitator runtime knobs. |
| **V5 Transparency** | PASS | Every shaping decision logs a `routing_log` row with score, retry-fired flag, retry-delta text, retry score, and per-stage timings (FR-011). Every register change emits one of three new `admin_audit_log` event types. |
| **V6 Graceful degradation** | PASS | Filler scorer fail-closes: regex bug, embedding-read failure, or sentence-transformers unavailability MUST persist the original draft with a `shaping_pipeline_error` routing-log row (spec edge case). The restatement signal individually degrades to `0.0` if spec 004's embedding pipeline is unavailable; the hedge + closing signals still contribute. |
| **V7 Coding standards** | PASS | All new functions stay within 25/5 limits. The scorer is a pure function over three signal helpers; the per-model profile dispatch is a dict lookup. |
| **V8 Data security** | PASS | No new secrets, no new data tier classification. Register override rows hold only an integer slider value, a facilitator ID, and a timestamp. No message content is read or stored by the shaping pipeline beyond the in-flight draft (immediately discarded after evaluation if not persisted). |
| **V9 Log integrity** | PASS | All audit events go through the existing append-only `admin_audit_log` path. `routing_log` extension follows spec 003's existing `@with_stage_timing` pattern. |
| **V10 AI security pipeline** | PASS | The shaping retry's tightened delta is a fixed-text Tier 4 delta (FR-013, Direct preset's text); no learned per-model deltas in v1. The tightened delta passes through the same canary-placed prompt assembly as the original draft, so any inbound-prompt protections still apply. |
| **V11 Supply chain** | PASS | No new dependencies. Reuse of spec 004's sentence-transformers is by reference to the already-loaded model — no new wheel, no new vendoring. |
| **V12 Topology compatibility** | PASS | Spec §V12 applies to topologies 1-6 (orchestrator-driven assembly); topology 7 (MCP-to-MCP) incompatibility flagged with reason in spec — no orchestrator-side prompt assembler to inject deltas into and no central post-output stage to score at. Same pattern as spec 013/014. |
| **V13 Use case coverage** | PASS | Spec §V13 maps to use cases §3 (Consulting Engagement — Direct preset + tight filler threshold) and §2 (Research Paper Co-authorship — per-participant override across registers). |
| **V14 Performance budgets** | PASS | Three V14 budgets in spec §"Performance Budgets" (filler scorer per draft <= 50ms P95, slider lookup O(1) < 1ms P95, shaping retry dispatch bounded by hardcoded 2-retry cap) with `routing_log` instrumentation per FR-011. |
| **V15 Fail-closed** | PASS | Invalid env vars exit at startup (FR-014); scorer pipeline errors fail closed to "persist original, log error" rather than gating the loop (spec edge case). |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Three new env vars (`SACP_FILLER_THRESHOLD`, `SACP_REGISTER_DEFAULT`, `SACP_RESPONSE_SHAPING_ENABLED`) require validators in `src/config/validators.py` (registered in `VALIDATORS` tuple) plus `docs/env-vars.md` sections with the six standard fields BEFORE `/speckit.tasks` (FR-014). Contract in [contracts/env-vars.md](./contracts/env-vars.md). |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/021-ai-response-shaping/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (env-vars, filler-scorer adapter, register-preset
│                        #                  interface, audit events)
├── checklists/          # Phase 1 output (requirements quality checklist)
├── spec.md              # Feature spec (input — not modified here)
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (repository root)

```text
src/
├── orchestrator/
│   ├── shaping.py                  # NEW — filler scorer (pure function over draft text +
│   │                               #       embedding); per-model BehavioralProfile dict;
│   │                               #       retry orchestration helpers
│   ├── convergence.py              # (from spec 004) — add `last_embedding` property and
│   │                               #                   `embedding_for_turn(n)` helper; two
│   │                               #                   single-line additions, no behavior
│   │                               #                   change
│   ├── loop.py                     # (existing) — wire shaping evaluation into the post-
│   │                               #              dispatch stage; FR-006 compound-retry
│   │                               #              budget integration
│   └── router.py                   # (existing) — extend per-turn dispatch return shape with
│                                   #              the shaping decision metadata for routing_log
├── prompts/
│   ├── register_presets.py         # NEW — frozen 1-5 preset registry; preset → Tier 4
│   │                               #       delta text mapping per FR-013
│   └── tiers.py                    # (existing) — extend `assemble_prompt` to accept a
│                                   #              register-preset delta and a shaping-retry
│                                   #              delta when a retry is firing
├── repositories/
│   ├── register_repo.py            # NEW — session_register and participant_register_override
│   │                               #       row CRUD with spec 001 cascade semantics
│   └── log_repo.py                 # (existing) — extend with shaping_routing_log helper and
│                                   #              register_audit_log helper
├── api/
│   └── me.py                       # (existing) — extend `/me` payload with register_slider,
│                                   #              register_preset, register_source per FR-010
├── config/
│   └── validators.py               # add three validators for the new SACP_* env vars
└── alembic/versions/
    └── 0XX_021_response_shaping.py # NEW — create session_register, participant_register_override;
                                    #       add routing_log shaping_* timing columns

tests/
├── test_021_filler_scorer.py            # NEW — US1 (P1) — score computation, threshold gating,
│                                        #                  retry firing, retry-budget exhaustion
├── test_021_register_session.py         # NEW — US2 (P2) — session-level slider mechanics,
│                                        #                  prompt assembly, /me reflection
├── test_021_register_override.py        # NEW — US3 (P3) — per-participant override scoping,
│                                        #                  cascade semantics
├── test_021_master_switch_disabled.py   # NEW — SC-002 regression: shaping pipeline off
│                                        #                          MUST be byte-identical to
│                                        #                          pre-feature behavior
├── test_021_shaping_pipeline_failure.py # NEW — fail-closed paths (regex bug, embedding read,
│                                        #                          sentence-transformers gone)
└── conftest.py                          # extend with hedge-heavy / restatement-heavy /
                                         # closing-heavy draft fixtures and the schema-mirror
                                         # raw DDL for the two new tables
```

**Structure Decision**: Single Python service consistent with existing layout. One new orchestrator module (`shaping.py`) holds the scorer and the per-model profile dispatch; one new prompts module (`register_presets.py`) holds the frozen 1-5 preset registry. The two new tables avoid a `sessions`-row column add (preserves spec 013's frozen-config baseline) and align with spec 001's atomic-delete cascade pattern.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations.)

## Phase 0 — Outline & Research

Open decisions queued for `research.md`:

1. **Per-model `BehavioralProfile` shape**. Spec FR-003 fixes the source (hardcoded dict in `src/orchestrator/shaping.py`, keyed by provider family). Research finalizes the dict's value shape — at minimum `(default_threshold, hedge_weight, restatement_weight, closing_weight)` per family, plus the question of whether to ship the per-model retry-delta text per family or share one delta across all retries. Default is "share one delta string" per spec assumption, but the dict shape MUST leave room for per-family overrides without a future schema break.
2. **Restatement-overlap signal mechanics with spec 004**. FR-001 / FR-012 fix the source (reuse `convergence_log.embedding` for prior 1-3 turns). Research selects the read path: in-memory property on `ConvergenceEngine` mirroring spec 014's `last_similarity` precedent (preferred — keeps it off the hot-path DB), or async DB read of `convergence_log.embedding` rows (worse — adds DB cost on every dispatch). Decision should be the in-memory property; finalize the property name and the buffer depth (last 3 turns).
3. **Filler-scorer normalization & weight tuning**. FR-002 fixes the aggregation as a weighted sum of three normalized signals with default weights `hedge=0.5, restatement=0.3, closing=0.2`. Research confirms the per-signal normalization rules: hedge ratio is naturally in `[0.0, 1.0]` (proportion of hedging tokens to total); restatement is cosine similarity in `[0.0, 1.0]` already; closing-pattern detection produces a count that needs an explicit cap (e.g., `min(matches, 3) / 3`). The hardcoded hedge token list and closing-pattern regex list need to be drafted from observed Phase 1+2 shakedown drafts.
4. **Retry-budget threading through the dispatch path**. FR-006 binds the shaping retry to the spec 003 §FR-031 compound-retry budget — each shaping retry consumes one budget slot. Research designs the integration point: does the dispatch loop in `loop.py` pre-debit the budget for the worst case (1 + 2 retries = 3 slots), or does it consume per-attempt as the scorer fires retries? Per-attempt is simpler but requires the dispatch loop to be re-entrant safely. Decision criterion: minimize surgery on the existing dispatch path.
5. **Register-state model — per-session vs per-participant resolution**. FR-007 / FR-008 / FR-009 / FR-010 imply two-row resolution at `/me` time: read participant's override row first, fall back to session row, fall back to `SACP_REGISTER_DEFAULT`. Research designs the lookup as either a single SQL JOIN at `/me` time (cleanest; one round trip per query) or a cached resolver on the session-runtime context (faster but adds invalidation surface for the override-set / session-slider-changed paths). Decision should favor the SQL JOIN unless `/me` is on the hot path and benchmarks justify the cache.
6. **`/me` payload extension shape**. FR-010 fixes three new fields. Research confirms the JSON serialization (snake_case to match existing `/me` field convention; `register_preset` as the canonical preset name string, not the slider integer; `register_source` as a two-value enum string). Existing `/me` has its own response model; the three fields are additive — no breaking change for clients that ignore unknown fields.
7. **Two-table vs one-table register persistence**. Spec Key Entities defers the decision to `/speckit.plan`: nullable column on `sessions` vs new `session_register` table for session-level slider; same for `ParticipantRegisterOverride`. Research recommends two new tables: keeps the `sessions` row narrow (matches spec 013's "frozen config + auxiliary mutable state in side tables" precedent) and lets the override table cleanly cascade-delete on participant or session removal (FR-015 / SC-007).
8. **Audit-event taxonomy for register changes**. FR-008 / FR-009 require audit-logging on session-slider change AND on per-participant override set/clear. Research selects the event-type names and their `previous_value` / `new_value` JSON shapes. Default proposal: three event types — `session_register_changed`, `participant_register_override_set`, `participant_register_override_cleared` — to keep set vs clear distinguishable in the audit log without a flag field.
9. **`SACP_FILLER_THRESHOLD` calibration default**. Spec ships a placeholder `0.6`. Research evaluates whether a single global default is appropriate or whether the per-model `BehavioralProfile` should override it per provider family (anthropic likely needs a higher threshold than groq, given observed verbosity tendencies). Decision: per-family default in the profile dict; the env var overrides only when set, otherwise the profile's family-default applies.
10. **Topology-7 forward note**. Spec V12 marks topology 7 incompatible. Research drafts the controller-side gate analogous to spec 014 §7: the shaping pipeline init checks `SACP_TOPOLOGY` env var and skips spawning when it equals `7`. Same forward-document pattern as spec 014.

Output: [research.md](./research.md) with one decision section per open question.

## Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **Data model** ([data-model.md](./data-model.md)) extracts entities from spec:
   - `BehavioralProfile` — frozen per-provider-family dict in `src/orchestrator/shaping.py`. Keys: provider family. Values: `(default_threshold, hedge_weight, restatement_weight, closing_weight, retry_delta_text)`.
   - `RegisterPreset` — frozen 1-5 mapping in `src/prompts/register_presets.py`. Keys: slider int. Values: `(preset_name, tier4_delta_text)`.
   - `SessionRegister` — DB table; one row per session; columns `(session_id, slider_value, set_by_facilitator_id, last_changed_at)`.
   - `ParticipantRegisterOverride` — DB table; zero-or-one row per participant; columns `(participant_id, session_id, slider_value, set_by_facilitator_id, last_changed_at)`. Cascades on participant delete and on session delete.
   - `FillerScore` (transient) — pure function output over a draft; logged to `routing_log` as a column triplet (score, retry_fired, retry_delta_text, retry_score) — not a standalone entity.
   - `ShapingDecision` (transient) — orchestrator-side per-turn record holding the original score, the retry-fired flag, the retry's score, and the persisted-draft selection. Logged to `routing_log` per FR-011; not a row in any other table.

2. **Contracts** ([contracts/](./contracts/)) — Phase 1 outputs four contract docs:
   - `contracts/env-vars.md` — three new vars with the six standard fields each (Default, Type, Valid range, Blast radius, Validation rule, Source spec).
   - `contracts/filler-scorer-adapter.md` — adapter contract for the filler scorer's three signal sources (hedge, restatement, closing); how each surfaces its normalized signal; how the per-model `BehavioralProfile` plugs in.
   - `contracts/register-preset-interface.md` — `RegisterPreset` registry contract; how the resolver reads (override → session → default) and how the resolved preset feeds the spec 008 Tier 4 hook.
   - `contracts/audit-events.md` — three new `admin_audit_log` action strings (`session_register_changed`, `participant_register_override_set`, `participant_register_override_cleared`); payload shapes.

3. **Quickstart** ([quickstart.md](./quickstart.md)) — operator workflow:
   - Enable shaping (set `SACP_RESPONSE_SHAPING_ENABLED=true` and `SACP_FILLER_THRESHOLD`, restart, observe `routing_log` shaping rows).
   - Tune the threshold based on observed retry firing.
   - Set the session register slider; observe `/me` reflection and prompt-assembly delta.
   - Set a per-participant override; verify isolation.
   - Disable / rollback (unset the master switch, restart).
   - Audit-log query examples for the three new register event types.

4. **Agent context update**: run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType claude` to merge Phase 3 tech into `CLAUDE.md`.

5. **Re-evaluate Constitution Check** post-design — confirm no V14/V15/V16 surfaces shifted from the pre-design table above. Phase 1 design preserves the V16 deliverable gate (FR-014) and adds no new fail-closed surfaces beyond those already enumerated.

**Output**: data-model.md, contracts/*.md, quickstart.md, updated CLAUDE.md.

## Notes for `/speckit.tasks`

- **V16 deliverable gate (FR-014)**: tasks MUST gate validator + doc work BEFORE any code-path work. The three new env vars (`SACP_FILLER_THRESHOLD`, `SACP_REGISTER_DEFAULT`, `SACP_RESPONSE_SHAPING_ENABLED`) need validator functions in `src/config/validators.py` registered in the `VALIDATORS` tuple, plus full sections in `docs/env-vars.md` with the six standard fields each. CI gate `scripts/check_env_vars.py` enforces drift detection; landing the validators + docs first keeps the master-switch test (SC-002) executable from the start.
- **Spec 004 hook precedence**: the `ConvergenceEngine.last_embedding` property (single-line addition, mirrors spec 014's `last_similarity` precedent) is a prerequisite for the restatement signal; tasks MUST land that hook before tasks that wire the restatement-signal call site.
- **Master-switch regression test (SC-002)**: re-runs every pre-feature acceptance test with `SACP_RESPONSE_SHAPING_ENABLED=false`. Should land EARLY in the task list as a canary for the additive-when-disabled guarantee.
- **Schema-mirror discipline**: any column added by the alembic migration MUST also be added to `tests/conftest.py` raw DDL. CI builds schema from conftest, not migrations; mismatch only surfaces in CI.
- **Retry-budget integration (FR-006)**: the shaping cap (hardcoded 2 retries) and the spec 003 §FR-031 compound-retry budget apply jointly — shaping stops at whichever cap fires first. Tasks should land the joint-cap test as a contract before either path's individual tests.
- **Compression boundary (FR-016)**: any task that touches `messages.content`, the rolling context window, or the persisted message body belongs to spec 026, not here. Reject any such task during `/speckit.tasks` review.
- **Spec 011 forward-ref**: the register-slider UI surface lands in spec 011 (orchestrator-controls UI) per the spec 011 amendment forward-ref. Tasks here ship only the `/me` field extension (server-side); the slider control widget is spec 011's deliverable. Per the spec-011 amendment reminder in user memory, ASK before drafting that surface.
- **Phase 3 declaration prerequisite**: the Phase 3 declaration recorded 2026-05-05 satisfies the phase gate. No additional dependency on spec 013 or 014 implementation status (spec 021 is independent of the high-traffic-mode controller stack — they share neither pipeline nor configuration).
