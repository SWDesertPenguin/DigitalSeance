---

description: "Task list for implementing spec 021 (AI response shaping — verbosity reduction + register slider)"
---

# Tasks: AI Response Shaping (Verbosity Reduction + Register Slider)

**Input**: Design documents from `/specs/021-ai-response-shaping/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — spec defines three Independent Tests + 13 Acceptance Scenarios across US1-US3, plus the SC-002 master-switch regression canary and three fail-closed pipeline edge cases. Tests land alongside implementation.

**Organization**: Tasks grouped by user story so each can be implemented and tested independently. Phase 2 covers shared infrastructure (V16 deliverable gate per spec 021 FR-014, schema migration with conftest mirror per memory `feedback_test_schema_mirror`, the spec 004 `last_embedding` hook, shared dataclasses, and the SC-002 regression canary).

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, OR independent functions in the same file with no shared edit point)
- **[Story]**: US1 / US2 / US3 (no label for Setup, Foundational, Polish)

## Path Conventions

Single project, paths under repo root. Backend code under [src/](src/); tests under [tests/](tests/) per [plan.md "Source Code"](./plan.md). The register-slider UI surface ships in spec 011 per the spec 011 amendment forward-ref — out of scope here.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repo hygiene + new module placeholders. Working tree is on `021-ai-response-shaping` branch off main.

- [ ] T001 Verify on branch `021-ai-response-shaping` and run `python scripts/check_env_vars.py` to confirm V16 baseline passes before any new validators land
- [ ] T002 [P] Create empty module skeletons: [src/orchestrator/shaping.py](./../../src/orchestrator/shaping.py), [src/prompts/register_presets.py](./../../src/prompts/register_presets.py), [src/repositories/register_repo.py](./../../src/repositories/register_repo.py) (each containing only a module docstring referencing spec 021)

---

## Phase 2: Foundational (Blocking Prerequisites — V16 Gate per FR-014)

**Purpose**: V16 env-var deliverables (3 validators + 3 docs sections), schema migration with conftest mirror, the spec 004 `last_embedding` hook, shared dataclasses, and the SC-002 regression canary. All three user stories depend on these.

**⚠️ CRITICAL**: No user-story task in Phase 3+ may begin until Phase 2 completes. The V16 gate is non-negotiable per spec FR-014.

### V16 deliverable gate (3 validators + 3 doc sections)

- [X] T003 [P] Add `validate_filler_threshold` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_FILLER_THRESHOLD](./contracts/env-vars.md): empty OR float in `[0.0, 1.0]`; out-of-range exits at startup
- [X] T004 [P] Add `validate_register_default` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_REGISTER_DEFAULT](./contracts/env-vars.md): empty OR int in `{1,2,3,4,5}`; out-of-set exits at startup
- [X] T005 [P] Add `validate_response_shaping_enabled` to [src/config/validators.py](./../../src/config/validators.py) per [contracts/env-vars.md §SACP_RESPONSE_SHAPING_ENABLED](./contracts/env-vars.md): empty OR `'true'/'false'` (case-insensitive) OR `'1'/'0'`; out-of-set exits at startup
- [X] T006 Append the three new validators to the `VALIDATORS` tuple at the bottom of [src/config/validators.py](./../../src/config/validators.py) (depends on T003-T005)
- [X] T007 [P] Add `### SACP_FILLER_THRESHOLD` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields per [contracts/env-vars.md](./contracts/env-vars.md)
- [X] T008 [P] Add `### SACP_REGISTER_DEFAULT` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields
- [X] T009 [P] Add `### SACP_RESPONSE_SHAPING_ENABLED` section to [docs/env-vars.md](./../../docs/env-vars.md) with the six standard fields
- [X] T010 Run `python scripts/check_env_vars.py` from repo root and confirm V16 CI gate green for the three new vars (validators + doc sections in lockstep)
- [X] T011 [P] Validator unit tests in [tests/test_021_validators.py](./../../tests/test_021_validators.py): each of the three validators — valid value passes, out-of-range raises `ConfigValidationError` naming the offending var, empty handled per the var's allowed-empty rule
  - Drift-detection regression: temporarily remove one of the three new sections from `docs/env-vars.md` AND run `python scripts/check_env_vars.py`; confirm the script exits non-zero AND names the missing section. Restore the section before exiting the test. (Verifies the V16 CI gate trips on validator-vs-docs drift, not just on present-and-aligned state.)

### Schema migration + conftest mirror (single landing per memory `feedback_test_schema_mirror`)

- [X] T012 Generate alembic migration `NNNN_021_response_shaping.py` in [alembic/versions/](./../../alembic/versions/) per [data-model.md "DB-persistent entities"](./data-model.md): create `session_register` table (PK `session_id` FK CASCADE; `slider_value` int CHECK 1-5; `set_by_facilitator_id`; `last_changed_at`) AND `participant_register_override` table (PK `participant_id` FK CASCADE; `session_id` FK CASCADE; `slider_value`; index on `session_id`); add five `routing_log` columns (`shaping_score_ms` int, `shaping_retry_dispatch_ms` int, `filler_score` numeric(4,3), `shaping_retry_delta_text` text, `shaping_reason` text) all NULL-default for backward compatibility; mirror the same DDL into [tests/conftest.py](./../../tests/conftest.py) raw DDL in the same task per memory `feedback_test_schema_mirror`

### Spec 004 hook + shared dataclasses

- [X] T013 [P] Add `last_embedding` property and `recent_embeddings(depth)` helper plus `_recent_embeddings: deque[bytes]` ring buffer (`maxlen=3`) to [src/orchestrator/convergence.py](./../../src/orchestrator/convergence.py) per [plan.md "Notes for /speckit.tasks"](./plan.md) and [data-model.md "Hooks introduced"](./data-model.md): single-line additions; populated wherever the existing convergence pipeline computes a turn embedding; no behavior change to spec 004
- [X] T014 [P] Implement `BehavioralProfile` frozen dataclass + `BEHAVIORAL_PROFILES` dict in [src/orchestrator/shaping.py](./../../src/orchestrator/shaping.py) per [contracts/filler-scorer-adapter.md](./contracts/filler-scorer-adapter.md) and [data-model.md §BehavioralProfile](./data-model.md): six provider-family entries (`anthropic`, `openai`, `gemini`, `groq`, `ollama`, `vllm`); each holds `(default_threshold, hedge_weight, restatement_weight, closing_weight, retry_delta_text)`; module-load assertion that the three weights sum to 1.0 per family
- [X] T015 [P] Implement `RegisterPreset` frozen dataclass + `REGISTER_PRESETS` tuple plus `preset_for_slider` and `preset_for_name` helpers in [src/prompts/register_presets.py](./../../src/prompts/register_presets.py) per [contracts/register-preset-interface.md](./contracts/register-preset-interface.md) and [data-model.md §RegisterPreset](./data-model.md): five-element tuple keyed by slider 1-5; canonical `tier4_delta` text per FR-013; slider 3 emits `None` for delta
- [X] T016 [P] Add `FillerScore` and `ShapingDecision` transient dataclasses to [src/orchestrator/shaping.py](./../../src/orchestrator/shaping.py) per [data-model.md "Transient (in-memory) entities"](./data-model.md)

### SC-002 regression canary

- [X] T017 [P] Regression canary [tests/test_021_master_switch_disabled.py](./../../tests/test_021_master_switch_disabled.py): assert no spec 021 shaping code path fires when `SACP_RESPONSE_SHAPING_ENABLED=false` (architectural test per spec.md SC-002 — runs early as a leak detector before US-phase code grows; the canary lands EARLY per [plan.md "Notes for /speckit.tasks"](./plan.md))

**Checkpoint**: V16 gate green; schema migration + conftest mirror landed; spec 004 hook in place; shared dataclasses available; SC-002 canary in place. User-story phases unblocked.

---

## Phase 3: User Story 1 — Filler scorer + retry (Priority: P1) 🎯 MVP

**Goal**: Filler scorer evaluates each AI draft on three signals (hedge ratio, restatement-cosine, closing-pattern), aggregates as a weighted sum per the per-family `BehavioralProfile`, and fires up to two tightened-Tier-4-delta retries when the score crosses `SACP_FILLER_THRESHOLD`. The first retry below threshold becomes the persisted draft; otherwise the second retry's output persists with `routing_log.reason='filler_retry_exhausted'`.

**Independent Test**: Drive a turn with a participant whose model is known to produce hedge-heavy output (synthesised via fixture or recorded transcript). Assert the orchestrator dispatches the turn, evaluates the response, computes a score above the configured threshold, fires up to two retries with the tightened delta, and persists the first retry whose score falls below threshold (or the second retry's output when both retries also exceed threshold). Verify `routing_log` rows reflect each retry event. Verify the transcript has exactly one message for that turn (the persisted draft, not any earlier hedge-heavy attempt).

### Tests for User Story 1

- [ ] T018 [P] [US1] Acceptance scenario 1 (over-threshold draft → tightened retry fires; only persisted draft enters transcript) in [tests/test_021_filler_scorer.py](./../../tests/test_021_filler_scorer.py)
- [ ] T019 [P] [US1] Acceptance scenario 2 (below-threshold draft → no retry; original draft enters transcript) in [tests/test_021_filler_scorer.py](./../../tests/test_021_filler_scorer.py)
- [ ] T020 [P] [US1] Acceptance scenario 3 (dispatch-path-level guarantee with `SACP_RESPONSE_SHAPING_ENABLED=false`): assert a DISTINCT property from T017 — with master switch off, the new `routing_log` columns (`shaping_score_ms`, `shaping_retry_dispatch_ms`, `filler_score`, `shaping_retry_delta_text`, `shaping_reason`) are NULL on every dispatch row (no value bleeding through), and the user-facing dispatch result (message content, dispatch counts, cost values) is byte-equal to a pre-feature baseline run. T017 is the architectural canary (no spec-021 code path fires); T020 is the row-introspection canary (no spec-021 column carries shaping-on values).
- [ ] T021 [P] [US1] Acceptance scenario 4 (both retries exceed threshold → second retry's draft persisted; `routing_log.reason='filler_retry_exhausted'`; no infinite loop) in [tests/test_021_filler_scorer.py](./../../tests/test_021_filler_scorer.py) — covers SC-003
- [ ] T022 [P] [US1] Acceptance scenario 5 (per-retry routing-log row records pre-retry score, tightened-delta text, post-retry score, per-stage timing) in [tests/test_021_filler_scorer.py](./../../tests/test_021_filler_scorer.py) — covers SC-006

### Implementation for User Story 1

- [X] T023 [P] [US1] Implement `_hedge_signal(draft_text)` in [src/orchestrator/shaping.py](./../../src/orchestrator/shaping.py) per [contracts/filler-scorer-adapter.md "Hedge-to-content ratio"](./contracts/filler-scorer-adapter.md): hardcoded `_HEDGE_TOKENS` tuple; case-insensitive matches over whitespace-split tokens; in `[0.0, 1.0]` by construction; empty draft returns `0.0`
- [X] T024 [P] [US1] Implement `_restatement_signal(draft_text, engine)` in [src/orchestrator/shaping.py](./../../src/orchestrator/shaping.py) per [contracts/filler-scorer-adapter.md "Restatement"](./contracts/filler-scorer-adapter.md): reads `engine.recent_embeddings(depth=3)` (depends on T013); reuses spec 004's `_compute_embedding_async` — no second sentence-transformers model load (FR-012); max cosine similarity returned; empty buffer or unavailable model → `0.0` with warning log per spec edge case
- [X] T025 [P] [US1] Implement `_closing_signal(draft_text)` in [src/orchestrator/shaping.py](./../../src/orchestrator/shaping.py) per [contracts/filler-scorer-adapter.md "Boilerplate closing detection"](./contracts/filler-scorer-adapter.md): hardcoded `_CLOSING_PATTERNS` regex tuple; capped count `min(matches, 3) / 3.0`; in `[0.0, 1.0]` by construction
- [X] T026 [US1] Implement `_aggregate(...)` and `compute_filler_score(draft_text, profile, engine)` in [src/orchestrator/shaping.py](./../../src/orchestrator/shaping.py) per [contracts/filler-scorer-adapter.md "Aggregation"](./contracts/filler-scorer-adapter.md) and FR-002: weighted sum using profile's per-family weights; depends on T023-T025
- [X] T027 [US1] Implement `profile_for(provider_family)` and `threshold_for(profile)` in [src/orchestrator/shaping.py](./../../src/orchestrator/shaping.py) per [contracts/filler-scorer-adapter.md "Threshold resolution"](./contracts/filler-scorer-adapter.md): env var `SACP_FILLER_THRESHOLD` overrides per-family default uniformly when set; FR-003 / research.md §9
- [X] T028 [US1] Implement `evaluate_and_maybe_retry(...)` in [src/orchestrator/shaping.py](./../../src/orchestrator/shaping.py) per [contracts/filler-scorer-adapter.md "Retry orchestration"](./contracts/filler-scorer-adapter.md): hardcoded `SHAPING_RETRY_CAP=2` (FR-004); joint cap with the participant's compound-retry budget per FR-006 — shaping stops at whichever cap fires first
  - Compound-budget exhaustion path: drive a participant whose compound-retry budget is at 1 (one slot remaining); when shaping triggers retry, assert (a) one shaping retry consumes the last compound slot, (b) shaping does NOT attempt a second retry even though `SHAPING_RETRY_CAP` would allow it, (c) the routing_log `shaping_reason` records `compound_retry_exhausted` (NOT `filler_retry_exhausted`).
- [ ] T029 [US1] Wire shaping evaluation into [src/orchestrator/loop.py](./../../src/orchestrator/loop.py) post-dispatch stage: call `evaluate_and_maybe_retry` after each provider dispatch when `SACP_RESPONSE_SHAPING_ENABLED=true`; SC-002 short-circuit when disabled; FR-001 / FR-005 / FR-006
- [ ] T030 [US1] Wire shaping-retry delta injection through [src/prompts/tiers.py](./../../src/prompts/tiers.py) `assemble_prompt`: add optional `shaping_retry_delta_text` parameter per [contracts/register-preset-interface.md "Prompt-assembly integration"](./contracts/register-preset-interface.md); appended after `custom_prompt` and after `register_delta_text`
- [ ] T031 [US1] Plumb the five new `routing_log` columns (`shaping_score_ms`, `shaping_retry_dispatch_ms`, `filler_score`, `shaping_retry_delta_text`, `shaping_reason`) through [src/repositories/log_repo.py](./../../src/repositories/log_repo.py) `log_routing` per FR-011 + [data-model.md "routing_log extension"](./data-model.md): each evaluation populates `shaping_score_ms`; each retry firing populates `shaping_retry_dispatch_ms`; reason is one of `null` / `'filler_retry'` / `'filler_retry_exhausted'` / `'shaping_pipeline_error'`
- [ ] T032 [US1] V14 stage-timing instrumentation: wrap `compute_filler_score` and the retry dispatch in `@with_stage_timing(stage_name='shaping_score_ms')` and `'shaping_retry_dispatch_ms'` respectively per [contracts/filler-scorer-adapter.md "Per-stage cost capture"](./contracts/filler-scorer-adapter.md); P95 ≤ 50ms scorer budget per spec §"Performance Budgets"

**Checkpoint**: US1 fully functional and testable independently. MVP increment: hedge-heavy drafts get one or two tightened-delta retries; below-threshold output replaces the original draft; shaping decisions are visible in `routing_log`.

---

## Phase 4: User Story 2 — Session register slider (Priority: P2)

**Goal**: Facilitator-controlled session register slider (1-5) selects among the five hardcoded `RegisterPreset` entries; the resolver emits the preset's Tier 4 delta into the prompt assembler; `/me` payload extends with `register_slider`/`register_preset`/`register_source`; every change writes a `session_register_changed` audit event.

**Independent Test**: Drive a session through facilitator-side slider changes (1 → 5 → 3). After each change, query `/me` for each participant and assert `register_slider`, `register_preset`, and `register_source='session'` reflect the new value. Inspect `admin_audit_log` for one entry per change with the actor (facilitator), target (session), old value, new value, and timestamp. Trigger a turn after each change and verify the assembled prompt contains the new preset's delta text (or no delta for slider 3).

### Tests for User Story 2

- [ ] T033 [P] [US2] Acceptance scenario 1 (facilitator sets slider → `session_register` row written + `session_register_changed` audit row with actor/target/old/new/timestamp) in [tests/test_021_register_session.py](./../../tests/test_021_register_session.py) — covers SC-004
- [ ] T034 [P] [US2] Acceptance scenario 2 (next turn after change → assembled prompt contains new preset's Tier 4 delta) in [tests/test_021_register_session.py](./../../tests/test_021_register_session.py) — covers SC-004
- [ ] T035 [P] [US2] Acceptance scenario 3 (slider=3 Balanced → assembled prompt contains NO register-specific delta — tier text alone) in [tests/test_021_register_session.py](./../../tests/test_021_register_session.py) — covers FR-007 / FR-013
- [ ] T036 [P] [US2] Acceptance scenario 4 (`/me` returns `register_slider`, `register_preset`, `register_source='session'` after a change for any participant without an override) in [tests/test_021_register_session.py](./../../tests/test_021_register_session.py) — covers FR-010
- [ ] T037 [P] [US2] Slider independence test: `SACP_RESPONSE_SHAPING_ENABLED=false` → slider deltas STILL emit (slider is a prompt-composition concern, not a shaping concern per spec edge case + [contracts/register-preset-interface.md "Independence from the master switch"](./contracts/register-preset-interface.md))

### Implementation for User Story 2

- [ ] T038 [US2] Implement `session_register` CRUD in [src/repositories/register_repo.py](./../../src/repositories/register_repo.py): `get_session_register(session_id)`, `upsert_session_register(session_id, slider_value, facilitator_id)`. Returns `SessionRegister` row or `None` per [data-model.md §session_register](./data-model.md)
- [ ] T039 [US2] Implement `resolve_register(participant_id, session_id, register_default, db)` in [src/repositories/register_repo.py](./../../src/repositories/register_repo.py) per [contracts/register-preset-interface.md "Resolver"](./contracts/register-preset-interface.md): single SQL JOIN with two LEFT JOINs and a COALESCE; returns `(slider_value, RegisterPreset, source)` per research.md §5
- [ ] T040 [US2] Extend session-control endpoint in [src/mcp_server/tools/facilitator.py](./../../src/mcp_server/tools/facilitator.py): new `/tools/facilitator/set_session_register` accepting `session_id` and `slider_value` (validated 1-5); calls `upsert_session_register`; emits `session_register_changed` audit event per [contracts/audit-events.md §session_register_changed](./contracts/audit-events.md); facilitator-only auth guard mirrors existing endpoints (FR-009)
- [ ] T041 [US2] Extend [src/api/me.py](./../../src/api/me.py) `/me` payload with three additive top-level fields (`register_slider`, `register_preset`, `register_source`) per FR-010 + [contracts/register-preset-interface.md "/me payload extension"](./contracts/register-preset-interface.md): calls `resolve_register` once per `/me` query; backward-compatible (existing clients ignore unknown fields)
- [ ] T042 [US2] Wire register-preset Tier 4 delta into [src/prompts/tiers.py](./../../src/prompts/tiers.py) `assemble_prompt` per [contracts/register-preset-interface.md "Prompt-assembly integration"](./contracts/register-preset-interface.md): new `register_delta_text` parameter — `None` for slider 3 (Balanced); appended after `custom_prompt` and before `shaping_retry_delta_text`; resolver runs unconditionally on every prompt assembly (slider is independent of master switch per spec edge case)
- [ ] T043 [US2] Audit-event emission helper in [src/repositories/log_repo.py](./../../src/repositories/log_repo.py) `log_register_change(action, target_id, previous_value, new_value, facilitator_id)`: writes through the existing append-only `admin_audit_log` path (V9); used by T040 (session-level) and US3 (override set/clear)

**Checkpoint**: US2 functional. Session register slider works end-to-end; the prompt assembler emits the correct delta per slider position; `/me` reflects the resolved register; audit log records every change.

---

## Phase 5: User Story 3 — Per-participant register override (Priority: P3)

**Goal**: Facilitator-set per-participant override that takes precedence over the session slider; isolated to the override-targeted participant only; cascade-deletes on participant or session removal per spec 001 §FR-011; every set/clear writes a `participant_register_override_set` or `_cleared` audit event (cascade events do NOT emit a register-cleared audit row per [research.md §8](./research.md)).

**Independent Test**: In a session with a session-level register, set a per-participant override on one participant. Verify their `/me` shows `register_source='participant_override'` while other participants still show `register_source='session'`. Drive turns and verify only the override-targeted participant's prompt contains the override's delta. Verify `admin_audit_log` has the override-set entry with all required fields. Pause and resume the session — override survives. Remove the participant — override row disappears (cascade).

### Tests for User Story 3

- [ ] T044 [P] [US3] Acceptance scenario 1 (override set → `/me` returns `register_source='participant_override'`; `participant_register_override_set` audit row written) in [tests/test_021_register_override.py](./../../tests/test_021_register_override.py)
- [ ] T045 [P] [US3] Acceptance scenario 2 (override scoping — other participants in same session unaffected, still `register_source='session'`) in [tests/test_021_register_override.py](./../../tests/test_021_register_override.py) — covers SC-005
- [ ] T046 [P] [US3] Acceptance scenario 3 (override-targeted participant's assembled prompt contains override's preset delta, NOT session-level preset's text) in [tests/test_021_register_override.py](./../../tests/test_021_register_override.py)
- [ ] T047 [P] [US3] Acceptance scenario 4 (pause-resume → override persists across pause cycle) in [tests/test_021_register_override.py](./../../tests/test_021_register_override.py)
- [ ] T048 [P] [US3] Acceptance scenario 5 (cascade on participant remove → override row gone; no orphan rows per FR-015 / SC-007) in [tests/test_021_register_override.py](./../../tests/test_021_register_override.py)
- [ ] T049 [P] [US3] Cascade test 2 (cascade on session delete → override row gone; no `participant_register_override_cleared` audit row emitted — parent delete event is sufficient per [research.md §8](./research.md)) in [tests/test_021_register_override.py](./../../tests/test_021_register_override.py)
  - Cascade-after-clear interleaving sub-test: facilitator clears a participant's override (emits `_cleared` event), THEN the session is deleted, THEN verify (a) no orphan `participant_register_override` row exists for that session_id, (b) the audit log records both the explicit clear AND the cascade-induced cleanup correctly without ambiguity. (Edge case: confirms the cascade-after-explicit-clear path produces clean state.)

### Implementation for User Story 3

- [ ] T050 [US3] Implement `participant_register_override` CRUD in [src/repositories/register_repo.py](./../../src/repositories/register_repo.py): `get_participant_override(participant_id)`, `upsert_participant_override(participant_id, session_id, slider_value, facilitator_id)`, `clear_participant_override(participant_id)`. Returns `ParticipantRegisterOverride` row or `None` per [data-model.md §participant_register_override](./data-model.md)
- [ ] T051 [US3] Extend `resolve_register` (T039) to read the override row first, fall back to the session row, fall back to `SACP_REGISTER_DEFAULT` per [contracts/register-preset-interface.md "Resolver"](./contracts/register-preset-interface.md). Source attribution: `'participant_override'` iff override row exists, else `'session'`
- [ ] T052 [US3] Extend session-control endpoint in [src/mcp_server/tools/facilitator.py](./../../src/mcp_server/tools/facilitator.py): new `/tools/facilitator/set_participant_register_override` (set/update — emits `participant_register_override_set`) and `/tools/facilitator/clear_participant_register_override` (explicit clear — emits `participant_register_override_cleared`); facilitator-only auth guard; payload shapes per [contracts/audit-events.md](./contracts/audit-events.md)
- [ ] T053 [US3] Override-only prompt-assembly path: when `resolve_register` returns `source='participant_override'`, the prompt assembler uses the override's preset delta; T042's wiring already supports this since the resolver returns the resolved preset directly (no separate code path needed — the override-vs-session distinction is encapsulated in the resolver)

**Checkpoint**: US3 functional. Per-participant overrides work end-to-end; isolation, cascade semantics, and audit-event distinction (explicit clear vs cascade) are all enforced.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Fail-closed pipeline tests, V14 perf instrumentation verification, quickstart validation, and cross-spec audit.

- [ ] T054 [P] Fail-closed pipeline tests in [tests/test_021_shaping_pipeline_failure.py](./../../tests/test_021_shaping_pipeline_failure.py) covering spec edge cases per [contracts/filler-scorer-adapter.md "Fail-closed contract"](./contracts/filler-scorer-adapter.md):
  - regex bug in `_HEDGE_TOKENS` or `_CLOSING_PATTERNS` raises → original draft persisted; `routing_log.shaping_reason='shaping_pipeline_error'`; no retry
  - `engine.recent_embeddings()` raises (embedding-read failure) → restatement signal returns `0.0`; aggregate proceeds with hedge + closing only; scorer continues
  - sentence-transformers unavailable / model raises → restatement signal returns `0.0` with warning log; hedge + closing still contribute (degrades gracefully rather than failing closed on the whole turn)
- [ ] T055 [P] Identical-output retry test: tightened-delta retry produces output IDENTICAL to original (model insensitivity to delta) → both drafts score identically; pipeline still consumes retry budget; second retry persists per FR-004's exhausted-retry rule; `routing_log` row records the equality per spec edge case
  - FR-016 byte-equal boundary assertion: after a shaping retry produces a final draft, assert the persisted `messages.content` for that turn equals the raw provider response from the retry attempt byte-for-byte (no truncation, no summarization, no shaping-side mutation). The shaping pipeline scores and orchestrates retries but MUST NOT alter persisted content.
- [ ] T056 [P] V14 perf-budget regression check: query `routing_log` to confirm `shaping_score_ms` p95 ≤ 50ms across the test corpus (V14 budget 1) and `shaping_retry_dispatch_ms` tracks the existing per-turn dispatch P95 (V14 budget 3)
- [ ] T057 Quickstart.md walk-through: operator workflow per [quickstart.md](./quickstart.md) Steps 1-6 (enable master switch → tune threshold → set session slider → set per-participant override → observe per-stage cost → disable/rollback). Run on a deployed orchestrator (Dockge stack) per memory `project_deploy_dockge_truenas`
- [ ] T058 [P] Cross-spec FR audit:
  - spec 003 §FR-030 `routing_log` per-stage timings: confirm `shaping_score_ms` and `shaping_retry_dispatch_ms` integrate with the existing `@with_stage_timing` pattern (T032)
  - spec 003 §FR-031 compound-retry budget: confirm joint-cap behavior — shaping retries consume budget slots per FR-006; shaping cap (2) and compound budget apply jointly (T028)
  - spec 004 hook: `ConvergenceEngine.last_embedding` (T013) is the only spec 004 amendment; no other behavior change
  - spec 008 Tier 4 hook: `assemble_prompt` extension with `register_delta_text` and `shaping_retry_delta_text` (T030 / T042) lands at the existing hook; no security-pipeline change (V3 / V10 preserved)
  - spec 001 §FR-008 immutability: persisted retry output is immutable like any other message; pre-persistence retry replacement is the only mutation (FR-016)
  - spec 001 §FR-011 atomic-delete: `participant_register_override` cascades on participant or session delete (T012 schema; T048 / T049 tests)
- [ ] T059 [P] Spec 011 amendment alignment: per memory `reminder_spec_011_amendments_at_impl_time`, ASK before drafting the register-slider UI surface in spec 011. Frontend module work for the slider control widget is spec 011's deliverable, not this spec's. The `/me` field extension (T041) is the only client-visible surface that lands here
- [ ] T060 [P] ruff + standards-lint pass: every commit on this branch passes the full pre-commit hook chain (gitleaks + 2ms + ruff + ruff-format + bandit + standards-lint 25/5)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — branch is already created from prior commit
- **Foundational (Phase 2)**: Depends on Setup — V16 gate (T003-T011) + schema (T012) + spec 004 hook + dataclasses (T013-T016) + canary (T017). BLOCKS all user stories
- **User Story 1 (Phase 3, P1)**: Depends on Phase 2 — primary value increment (filler scorer + retry pipeline)
- **User Story 2 (Phase 4, P2)**: Depends on Phase 2; reuses prompt-assembler hook from US1 (T030) and audit-event helper (T043)
- **User Story 3 (Phase 5, P3)**: Depends on US2 (resolver + audit-event helper); the override extends the session-level resolver
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies (recap)

- **US1**: Phase 2 → US1 (no story dependencies)
- **US2**: Phase 2 → US2; reuses `assemble_prompt` extension from US1 (T030)
- **US3**: US2 → US3 (the override resolver builds on the session-level resolver)

### Within Each User Story

- Tests (which are included for this spec) MUST be written and FAIL before implementation per the test-first convention from Phase 2's SC-002 canary
- Models / dataclasses before services; services before endpoints; endpoints before routing_log emissions
- Spec 004 hook (T013) is a prerequisite for the restatement signal (T024) per [plan.md "Notes for /speckit.tasks"](./plan.md)

### Parallel Opportunities

- All Phase 2 [P] validator + doc tasks (T003-T009, except T006 and T010 which aggregate / verify) can run in parallel
- All Phase 2 [P] dataclass tasks (T013-T017) can run in parallel — different files
- All [P] test tasks within a user story can run in parallel
- Implementation tasks across user stories (US1 + US2) can run in parallel after Phase 2 if team capacity allows
- Three signal helpers in US1 (T023, T024, T025) can run in parallel — different functions in the same file with no shared edit point
- All Phase 6 [P] polish tasks can run in parallel

---

## Parallel Example: Phase 2 V16 deliverable gate

```bash
# Three validator additions in src/config/validators.py (different functions, no shared edit point):
Task: "T003 [P] validate_filler_threshold"
Task: "T004 [P] validate_register_default"
Task: "T005 [P] validate_response_shaping_enabled"

# Three docs/env-vars.md sections in parallel:
Task: "T007 [P] SACP_FILLER_THRESHOLD section"
Task: "T008 [P] SACP_REGISTER_DEFAULT section"
Task: "T009 [P] SACP_RESPONSE_SHAPING_ENABLED section"

# Then T006 (append to VALIDATORS tuple) + T010 (CI gate verification) run sequentially.
```

---

## Parallel Example: User Story 1 signal helpers

```bash
# All three signal helpers in src/orchestrator/shaping.py — different functions, no shared edit point:
Task: "T023 [P] [US1] _hedge_signal — hedge-to-content ratio"
Task: "T024 [P] [US1] _restatement_signal — cosine vs prior turns"
Task: "T025 [P] [US1] _closing_signal — boilerplate closing detection"

# Aggregator and dispatch wiring run sequentially after the three signals land:
Task: "T026 [US1] compute_filler_score (depends on T023-T025)"
Task: "T028 [US1] evaluate_and_maybe_retry (depends on T026, T027)"
Task: "T029 [US1] loop.py post-dispatch wiring (depends on T028)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (V16 gate + schema + spec 004 hook + dataclasses + canary — all blocking)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Drive a hedge-heavy session and verify the filler scorer + retry pipeline produces tighter persisted drafts; confirm `routing_log` shaping decisions are captured
5. Deploy / demo if ready (filler scorer + retry only; register slider US2 / US3 deferred)

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 → MVP (filler scorer catches structural padding at generation time)
3. US2 → session-level register slider; facilitator UX
4. US3 → per-participant override; mixed-register session UX
5. Polish → fail-closed tests, V14 perf verification, quickstart walk-through, cross-spec audit

### Parallel Team Strategy

With multiple developers after Phase 2:

- Developer A: US1 (P1 MVP — filler scorer + retry)
- Developer B: US2 (P2 register slider — can land in parallel with US1 once T030 prompt-assembler hook exists)
- Developer C: Phase 6 polish prep (fail-closed test scaffolds T054 — pure test work, can land alongside US1)

US3 is sequential after US2 since it extends the session-level resolver. Polish closes out after all three user stories.

---

## Notes

- [P] tasks = different files OR independent functions in the same file with no shared edit point (e.g., three validator functions in `src/config/validators.py` are P; the `VALIDATORS` tuple append is not)
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing (the SC-002 canary is the foundational example)
- Per memory `feedback_test_schema_mirror`: alembic migration + `tests/conftest.py` raw DDL update MUST land in the same task (T012) — CI builds schema from conftest, not migrations
- Per memory `reminder_spec_011_amendments_at_impl_time`: ASK before drafting the register-slider UI surface in spec 011 — frontend slider widget is spec 011's deliverable, not this spec's
- Per memory `feedback_no_auto_push`: do not push the branch upstream without explicit confirmation
- Per spec FR-016 (compression boundary): NO task may touch `messages.content`, the rolling context window, or the persisted message body — that work belongs to spec 026 (context compression), out of scope here
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence (US3 depends on US2 by design — that dependency is explicit in the dependency graph above and not hidden)
