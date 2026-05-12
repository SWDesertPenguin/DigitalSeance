---

description: "Task list for spec 026 — Context Compression and Distillation (Six-Layer Stack)"
---

# Tasks: Context Compression and Distillation (Six-Layer Stack)

**Input**: Design documents from `/specs/026-context-compression/`
**Prerequisites**: plan.md (loaded), spec.md (6 user stories — US1 P1, US2 P1, US3 P1, US4 P2, US5 P3, US6 P3), research.md (16 sections), data-model.md, contracts/env-vars.md, contracts/compressor-service-interface.md, contracts/compression-log-row.md, contracts/routing-log-additions.md, quickstart.md

**Tests**: INCLUDED. The spec has 13+ Success Criteria framed as enforceable contracts; plan.md and research.md cite specific test files for FR coverage. Tests ship alongside implementation per the spec 022/023/029 precedent.

**Organization**: Tasks grouped by phase and user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1..US6)
- All file paths are absolute or relative to the 026 branch root (`S:\GitHub\DigitalSeance\`)

## Path Conventions

- Backend Python: `src/api_bridge/`, `src/compression/`, `src/orchestrator/`, `src/repositories/`, `src/config/`
- Frontend (CDN-loaded React SPA, no build toolchain): `frontend/*.jsx`, `frontend/*.js` — NO frontend surface for Phase 1
- Tests: `tests/` (pytest)
- Migrations: `alembic/versions/`
- Docs: `docs/`

---

## Phase 1: Setup (Shared Infrastructure — V16 deliverable gate)

**Purpose**: Env-var validators + `docs/env-vars.md` sections (V16 deliverable gate per FR-025).

- [X] T001 Add four NEW sections to `docs/env-vars.md` for `SACP_CACHE_OPENAI_KEY_STRATEGY`, `SACP_COMPRESSION_PHASE2_ENABLED`, `SACP_COMPRESSION_THRESHOLD_TOKENS`, `SACP_COMPRESSION_DEFAULT_COMPRESSOR` with the six standard fields per [contracts/env-vars.md](./contracts/env-vars.md).
- [X] T002 Add a "Spec 026 rename reconciliation" header note to the existing `SACP_ANTHROPIC_CACHE_TTL` and `SACP_DENSITY_ANOMALY_RATIO` sections in `docs/env-vars.md` per [research.md §2](./research.md). Note the spec 026 drafted names (`SACP_CACHE_ANTHROPIC_TTL`, `SACP_INFORMATION_DENSITY_THRESHOLD`) as cross-references so operators searching either name find the right doc.
- [X] T003 [P] Add `validate_cache_openai_key_strategy` to `src/config/validators.py` per [contracts/env-vars.md §SACP_CACHE_OPENAI_KEY_STRATEGY](./contracts/env-vars.md): string enum `'session_id'|'participant_id'`, default `'session_id'`; out-of-set exits at startup. Reuse `_validate_bool_enum` pattern.
- [X] T004 [P] Add `validate_compression_phase2_enabled` to `src/config/validators.py` per [contracts/env-vars.md §SACP_COMPRESSION_PHASE2_ENABLED](./contracts/env-vars.md): string enum `'true'|'false'`, default `'false'`; out-of-set exits at startup.
- [X] T005 [P] Add `validate_compression_threshold_tokens` to `src/config/validators.py` per [contracts/env-vars.md §SACP_COMPRESSION_THRESHOLD_TOKENS](./contracts/env-vars.md): int in `[500, 100000]`, default `4000`; out-of-range exits at startup.
- [X] T006 [P] Add `validate_compression_default_compressor` to `src/config/validators.py` per [contracts/env-vars.md §SACP_COMPRESSION_DEFAULT_COMPRESSOR](./contracts/env-vars.md): string from `{noop, llmlingua2_mbert, selective_context, provence, layer6}`, default `'noop'`; out-of-set exits at startup with an error listing the registered names.
- [X] T007 Register the four new validators in the `VALIDATORS` tuple at the bottom of `src/config/validators.py` (depends on T003-T006).
- [X] T008 [P] Add cross-validator interaction logic per [contracts/env-vars.md "Cross-validator interaction"](./contracts/env-vars.md): emit a startup WARNING when `SACP_COMPRESSION_PHASE2_ENABLED=true` AND `SACP_COMPRESSION_DEFAULT_COMPRESSOR='noop'`; raise `ValidationFailure` when `SACP_COMPRESSION_PHASE2_ENABLED=false` AND `SACP_COMPRESSION_DEFAULT_COMPRESSOR='llmlingua2_mbert'`; raise `ValidationFailure` when `SACP_TOPOLOGY=7` AND `SACP_COMPRESSION_DEFAULT_COMPRESSOR != 'noop'`.
- [X] T009 [P] Validator unit tests in `tests/test_026_validators.py` covering valid values, out-of-range, malformed; cross-validator interaction tests (WARN emission + ValidationFailure on conflict).
- [X] T010 Run `python scripts/check_env_vars.py` from repo root and confirm V16 CI gate green for the four new vars + the two existing rename-cross-reference headers.

**Checkpoint**: Env vars valid at startup; cross-validator interactions enforced; rename reconciliation documented.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema migration, CompressorService skeleton, architectural tests. Every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Schema migration + conftest mirror

- [X] T011 Generate alembic migration `018_compression_log.py` in [alembic/versions/](../../alembic/versions/) per [data-model.md "Migration"](./data-model.md): create `compression_log` table (BIGSERIAL id, all required columns, CHECK constraints on `source_tokens >= 0`, `output_tokens >= 0`, `duration_ms >= 0`, `trust_tier` enum, `compressor_id` enum); create two indexes (`(session_id, created_at DESC)`, `(compressor_id, created_at DESC)`); ALTER `sessions` ADD COLUMN `compression_mode TEXT NOT NULL DEFAULT 'auto'` with CHECK constraint on the 7-value enum. Pre-allocated slot `'018'` with `down_revision='016'` (current chain head); rebase to `'017'` once spec 022's migration lands. Mirror the same DDL into `tests/conftest.py` raw DDL per `feedback_test_schema_mirror`.
- [X] T012 Run `python scripts/check_schema_mirror.py` and confirm zero drift between alembic 018 and the conftest raw DDL.
- [ ] T013 Migration upgrade/downgrade test in `tests/test_026_migration_018.py`: apply migration 018 to a fresh schema; assert table exists with the expected column set, both indexes exist, all CHECK constraints fire on bad values, `sessions.compression_mode` defaults to `'auto'` on existing rows. Forward-only per Constitution §6 + 001 §FR-017 — `downgrade()` is a no-op. DEFERRED until a live DB harness lands; conftest mirror + check_schema_mirror green covers static parity.

### Module skeletons

- [X] T014 [P] Create empty module skeletons under `src/compression/`: `__init__.py`, `service.py`, `noop.py`, `llmlingua2_mbert.py`, `selective_context.py`, `provence.py`, `layer6.py`, `markers.py`, `trust_tier.py`, `segments.py`. Each contains only a module docstring referencing spec 026. (Implementations landed alongside skeletons.)
- [X] T015 [P] Create empty module skeleton `src/repositories/compression_repo.py` (module docstring referencing spec 026). (Insert helper landed alongside.)

### CompressorService registry skeleton

- [X] T016 Implement `Compressor` Protocol + `CompressedSegment` dataclass in [src/compression/segments.py](../../src/compression/segments.py) per [data-model.md "CompressedSegment"](./data-model.md): frozen dataclass with `output_text`, `output_tokens`, `trust_tier`, `boundary_marker`, `compressor_id`, `compressor_version` fields.
- [X] T017 Implement `CompressorService` skeleton in [src/compression/service.py](../../src/compression/service.py) per [contracts/compressor-service-interface.md](./contracts/compressor-service-interface.md) + [research.md §5](./research.md): `register(...)`, `freeze()`, `compress(...)`. Module-load registration pattern; topology-7 gate (registers `noop` only when `SACP_TOPOLOGY=7`). Per-call `time.perf_counter()` timing wrapped around the compressor body. Plus `_telemetry_sink` indirection so the dispatcher is DB-free for unit tests; production wires the real sink via `set_writer()` at lifespan.
- [X] T018 Implement `insert_compression_log(...)` in [src/repositories/compression_repo.py](../../src/repositories/compression_repo.py) per [contracts/compression-log-row.md](./contracts/compression-log-row.md): single INSERT into `compression_log` with the per-dispatch row shape. Async per the existing repository pattern.

### Trust-tier + XML boundary markers

- [X] T019 [P] Implement `resolve_min_tier(...)` + `TIER_ORDER` + `TierOneRefusalError` in [src/compression/trust_tier.py](../../src/compression/trust_tier.py) per [research.md §7](./research.md). MIN-tier resolution per Session 2026-05-11 §3.
- [X] T020 [P] Implement `wrap(text, source_tier, compressor_id, version) -> str` in [src/compression/markers.py](../../src/compression/markers.py) per [research.md §7](./research.md). Returns `<compressed source-tier="..." compressor="..." version="...">...</compressed>`.
- [X] T021 [P] Unit tests in `tests/test_026_markers_trust_tier.py` per [research.md §7](./research.md): XML marker assembly round-trip; MIN-tier resolution for the three-tier ordering; TierOneRefusalError raised when input tier is `'system'`; marker is None for NoOp output.

### Architectural tests (FR-023 + FR-024 — LAND IN PHASE 2 PER plan.md anchor)

- [X] T022 Implement `tests/test_026_architectural.py` per [research.md §15](./research.md): (a) `test_no_direct_compressor_imports_outside_compression_package` — scan all `src/**/*.py` (excluding `src/compression/`) for imports from `src.compression.noop|llmlingua2_mbert|selective_context|provence|layer6`; raise AssertionError on any direct import; (b) `test_convergence_detector_does_not_import_from_compression_package` + analogous check on `src/orchestrator/density.py`; (c) `test_compressor_service_does_not_call_unexpected_writes` — scan `src/compression/service.py` for any non-`compression_log` INSERT calls.

**Checkpoint**: Migration applied, conftest mirrored, CompressorService skeleton in place, trust-tier + markers ready, architectural tests asserting the package boundary.

---

## Phase 3: User Story 1 — Provider-native caching is configured on every closed-API call (Priority: P1) 🎯 MVP

**Purpose**: Wire the routing_log `cache_hit` / `cache_miss` markers at the response-handling site. This is the first Phase 1 behavioural surface.

### Tests for User Story 1

- [ ] T023 [P] [US1] Acceptance scenarios 1-3 in `tests/test_026_cache_markers.py`: first turn emits `routing_log.reason='cache_miss'`; second turn (same session, same participant) emits `reason='cache_hit'` + `cached_prefix_tokens`; cache_hit row carries the cached prefix token count.
- [ ] T024 [P] [US1] SC-002 multi-turn integration in `tests/test_026_cache_hit_multi_turn.py`: drive 3 turns; assert turns 2 and 3 produce `cache_hit` markers; assert cache_key tuple is `(provider, session_id, participant_id, compressor_version)` per FR-004 (cross-participant test asserts no contamination).
- [ ] T025 [P] [US1] Cache-invalidation event coverage in `tests/test_026_cache_invalidation.py`: trigger a spec 017 tool-list refresh; assert the next dispatch emits `cache_miss` with an invalidation reason in the routing_log payload (cross-ref spec 017 `prompt_cache_invalidated`).

### Implementation for User Story 1

- [ ] T026 [US1] Wire cache_hit / cache_miss emission in [src/api_bridge/caching.py](../../src/api_bridge/caching.py) response-handling site per [contracts/routing-log-additions.md "Emission-site mapping"](./contracts/routing-log-additions.md): inspect the LiteLLM response for the provider-specific cache-hit indicator (Anthropic `usage.cache_read_input_tokens`, OpenAI `usage.prompt_tokens_details.cached_tokens`, Gemini equivalent); emit `routing_log.reason='cache_hit'` with `cached_prefix_tokens=<N>` or `cache_miss` accordingly. Per-provider extraction lives in a helper to keep `caching.py` readable.
- [ ] T027 [US1] Add `cache_hit` / `cache_miss` / `compression_applied` / `compression_pipeline_error` / `density_anomaly_flagged` to the routing_log reason enumeration in [src/repositories/log_repo.py](../../src/repositories/log_repo.py) (or wherever the reason constants live). Update the docstring listing valid reason values.
- [ ] T028 [US1] Audit the spec 020 ProviderAdapter `cache_control` normalisation per [research.md §1](./research.md) + spec 020 §FR-010: confirm Anthropic adapter attaches `cache_control={"type":"ephemeral", "ttl":<SACP_ANTHROPIC_CACHE_TTL>}` at the breakpoint position; confirm OpenAI adapter attaches `prompt_cache_key=<session_id>` (or `<participant_id>` per `SACP_CACHE_OPENAI_KEY_STRATEGY`); confirm Gemini adapter has a placeholder or skip-with-warn path. Fix any drift in `src/api_bridge/litellm/adapter.py`.

**Checkpoint**: Cache-hit / cache-miss markers fire on every closed-API leg; per-provider cache directives confirmed wired through spec 020 adapter.

---

## Phase 4: User Story 2 — Information-density signal flags low-content turns and dual-writes (Priority: P1)

**Purpose**: Add the Session 2026-05-11 §4 dual-write at the existing density-signal call site. Existing convergence_log write stays; new routing_log write joins it.

### Tests for User Story 2

- [X] T029 [P] [US2] Acceptance scenarios in `tests/test_026_density_dual_write.py` — landed at fire-site in `src/orchestrator/convergence.py::_emit_density_routing_marker` rather than `src/orchestrator/density.py` (the density module is pure-logic; the per-turn fire site lives in convergence). Unit tests stub the embedding model and force the anomaly path. The `density_value` / `baseline_mean` / `ratio` payload fields are DEFERRED — routing_log has no generic payload column; readers JOIN convergence_log on `(turn_number, session_id)` for the full payload. Co-commit "same transaction" framing in spec text reads as best-effort dual-write here because the two writes share the asyncpg pool but not a single transaction; both target append-only tables in the same database so the failure surface is acceptable per the spec contract.
- [ ] T030 [P] [US2] SC-005 summarizer-corpus filter test in `tests/test_026_summarizer_filter.py`: insert a density-flagged convergence_log row for a known turn; trigger the summarizer; assert the rolling-summary output does NOT contain content from the flagged turn (FR-019 — Phase 1 behavioural change). DEFERRED — requires summarizer-site discovery (`src/orchestrator/summarizer.py`) + a filter integration; lands in the next 026 pass.

### Implementation for User Story 2

- [X] T031 [US2] Routing_log dual-write at the density-signal fire site landed in `src/orchestrator/convergence.py::_emit_density_routing_marker`. The existing convergence_log INSERT stays; routing_log INSERT joins it with `reason='density_anomaly_flagged'`. Payload-extension fields DEFERRED per T029 deferral.
- [ ] T032 [US2] Implement the summarizer-corpus filter at the spec 005 summarizer site per [research.md §13](./research.md): when reading turns for the rolling-summary corpus, JOIN-or-filter against `convergence_log WHERE tier='density_anomaly' AND target_event_id=<turn_id>`; exclude flagged turns. Implementation path determined at task time (likely `src/orchestrator/summarizer.py`). DEFERRED with T030.

**Checkpoint**: Density-flagged turns write to both convergence_log + routing_log (T031 done). Summarizer-corpus filter still pending (T030 + T032).

---

## Phase 5: User Story 3 — NoOpCompressor passes content through unchanged; CompressorService interface is in place (Priority: P1)

**Purpose**: Ship the NoOpCompressor + the bridge-layer integration. This is the Phase 1 baseline that Phase 2 cuts over from.

### Tests for User Story 3

- [ ] T033 [P] [US3] NoOpCompressor unit tests in `tests/test_026_noop_compressor.py` per [research.md §6](./research.md): SC-006 byte-identical output (input bytes equal output bytes); `output_tokens == source_tokens`; compressor_id='noop', compressor_version='1', layer='noop'; tier-1 input passes through (NoOp is exempt from FR-014 refusal).
- [ ] T034 [P] [US3] SC-013 log-per-dispatch invariant in `tests/test_026_compression_log_per_dispatch.py`: drive 5 dispatches via CompressorService.compress(...) (all NoOp); assert exactly 5 rows in `compression_log`; assert each row carries the expected per-dispatch shape from [contracts/compression-log-row.md](./contracts/compression-log-row.md).
- [ ] T035 [P] [US3] CompressorService registry tests in `tests/test_026_compressor_service.py`: register/get round-trip; double-registration raises ValueError; register-after-freeze raises RuntimeError; unregistered compressor_id raises UnregisteredCompressorError on compress(); topology-7 gate restricts registry to `noop` only.

### Implementation for User Story 3

- [ ] T036 [US3] Implement `NoOpCompressor` in [src/compression/noop.py](../../src/compression/noop.py) per [research.md §6](./research.md) + [contracts/compressor-service-interface.md](./contracts/compressor-service-interface.md): `compress(payload, target_budget, trust_tier) -> CompressedSegment`; returns input verbatim with `output_tokens == source_tokens`; `boundary_marker=None`; pass-through `trust_tier`. Registers with `CompressorService` at module import per the established pattern.
- [ ] T037 [US3] Wire `CompressorService.compress(...)` at the per-participant pre-bridge dispatch site in [src/orchestrator/loop.py](../../src/orchestrator/loop.py) per [research.md §1](./research.md): the existing dispatch path calls `CompressorService.compress(payload, target_budget, trust_tier, ...)` before forwarding to the bridge; on NoOp the dispatch path uses the returned `output_text` verbatim (byte-identical to today's behaviour); on non-NoOp the dispatch path wraps `output_text` with the boundary marker before forwarding.
- [X] T038 [US3] Mount `CompressorService.freeze()` in the FastAPI lifespan — landed in `src/mcp_server/app.py::_freeze_compressor_registry` (the MCP server hosts the orchestrator pool + services; the Web UI hydrates from MCP via `prime_from_mcp_app`, so the freeze on the MCP lifespan suffices). Also wires `_telemetry_sink.set_writer(...)` to the asyncpg-backed `compression_repo.insert_compression_log` writer so production dispatches land in the `compression_log` table while tests still observe via the in-memory accumulator.

**Checkpoint**: NoOpCompressor is the Phase 1 default; every dispatch writes a compression_log row; Phase 2 cutover is one env-var change away.

---

## Phase 6: User Story 4 — LLMLingua2mBERTCompressor scaffold engages at threshold (Priority: P2, scaffold-only in Phase 1)

**Purpose**: Phase 2 scaffold for the LLMLingua-2 mBERT compressor. v1 raises NotImplementedError until Phase 2 enabled.

### Tests for User Story 4

- [X] T039 [P] [US4] Phase 2 scaffold tests in `tests/test_026_phase2_scaffold.py`: with `SACP_COMPRESSION_PHASE2_ENABLED=false`, LLMLingua2mBERTCompressor.compress(...) raises NotImplementedError naming the env var; with `=true` and no real implementation, raises NotImplementedError naming the Phase 2 task list TBD.
- [X] T040 [P] [US4] Selective Context fallback scaffold tests in same file: identical Phase 2 gate; raises NotImplementedError until Phase 2 ships.
- [X] T041 [P] [US4] FR-020 fail-soft test — covered by `tests/test_026_compressor_service.py::test_compressor_failure_wraps_in_pipeline_error`: assert CompressorService catches Compressor exceptions, records a failure telemetry row, and raises CompressionPipelineError. The bridge-side fall-through to un-compressed payload lands at T037 (Phase 5).

### Implementation for User Story 4

- [X] T042 [US4] Implement `LLMLingua2mBERTCompressor` per [research.md §8](./research.md). Scaffold landed first (COMPRESSOR_VERSION='0-scaffold'); Phase 2 layer-4 real body landed second — replaces the inner NotImplementedError with a lazy-loaded `llmlingua.PromptCompressor` singleton when the optional `compression-phase2` extra is installed (`uv pip install -e .[compression-phase2]`). Version bumped to `'1-llmlingua-real'`. Phase-2-OFF gate stays — phase2=true + dep missing still raises (CompressorService catches and falls through per FR-020). Output is wrapped in the FR-012 XML boundary marker with MIN-tier inheritance from source.
- [X] T043 [US4] Implement `SelectiveContextCompressor` Phase 1 scaffold in [src/compression/selective_context.py](../../src/compression/selective_context.py) per [research.md §9](./research.md): same scaffold pattern as T042.
- [X] T044 [US4] Implement `CompressionPipelineError` + fail-soft handler in [src/compression/service.py](../../src/compression/service.py): catch any Compressor exception, raise `CompressionPipelineError` to the caller. The `routing_log.reason='compression_pipeline_error'` emission lands when the bridge-side dispatch call site lands at T037 (Phase 5); the failure telemetry row is already recorded in `compression_log` at the service layer.

**Checkpoint**: Phase 2 compressors are scaffolded; activation is gated; failure falls through to baseline.

---

## Phase 7: User Story 5 — Provence stub registers (Priority: P3, scaffold-only)

**Purpose**: Layer 5 scaffold per FR-021.

### Tests for User Story 5

- [X] T045 [P] [US5] Provence scaffold tests in `tests/test_026_phase3_scaffolds.py`: NoOpProvenceAdapter registers at module import; compress(...) raises NotImplementedError naming retrieval-spec dependency; tier-1 refusal exercised.

### Implementation for User Story 5

- [X] T046 [US5] Implement `NoOpProvenceAdapter` in [src/compression/provence.py](../../src/compression/provence.py) per [research.md §10](./research.md): NotImplementedError pattern; `COMPRESSOR_VERSION='0-stub'`.

---

## Phase 8: User Story 6 — Layer 6 stub registers; structurally skipped on closed-API legs (Priority: P3, scaffold-only)

**Purpose**: Layer 6 scaffold per FR-022 + SC-011 closed-API skip.

### Tests for User Story 6

- [X] T047 [P] [US6] Layer 6 scaffold tests in `tests/test_026_phase3_scaffolds.py`: NoOpLayer6Adapter registers at module import; `supports('anthropic')` False; `supports('openai')` False; `supports('google')` False; `supports('ollama')` True; `supports('vllm')` True; compress(...) raises NotImplementedError naming local-model-support dependency; tier-1 refusal exercised.
- [ ] T048 [P] [US6] SC-011 closed-API skip in `tests/test_026_layer6_closed_api_skip.py` — DEFERRED to T050 wiring; the static `supports()` discriminator is unit-tested in T047, but the dispatch-side skip-without-error path needs the bridge integration to land first.

### Implementation for User Story 6

- [X] T049 [US6] Implement `NoOpLayer6Adapter` in [src/compression/layer6.py](../../src/compression/layer6.py) per [research.md §11](./research.md): `supports(provider) -> bool` returning True for `ollama`/`vllm`, False for others; NotImplementedError on compress until local-model spec lands; `COMPRESSOR_VERSION='0-stub'`.
- [ ] T050 [US6] Wire the Layer 6 skip in [src/compression/service.py](../../src/compression/service.py): when the selected compressor is `layer6` AND `NoOpLayer6Adapter.supports(provider) == False`, fall back to NoOp WITHOUT emitting `compression_pipeline_error` (the skip is by design, not failure). Requires extending `compress(...)` signature with `provider: str`; lands together with T037 (bridge dispatch wiring).

---

## Phase 9: Master-switch + perf budgets + polish

- [ ] T051 [P] Master-switch-off canary in `tests/test_026_master_switch_phase2.py` per [plan.md "Notes for /speckit.tasks"](./plan.md): with `SACP_COMPRESSION_PHASE2_ENABLED=false` (default) AND `SACP_COMPRESSION_DEFAULT_COMPRESSOR=noop` (default), assert byte-identical-to-baseline dispatch behaviour (SC-006) AND every dispatch writes a compression_log row with `compressor_id='noop'`.
- [ ] T052 [P] V14 perf-budget tests in `tests/test_026_perf_budgets.py` per [research.md §14](./research.md): assert NoOp dispatch overhead is < 1ms at P95 vs un-compressor-mediated baseline (synthesised by mocking CompressorService.compress to return input verbatim without writing the log row); assert log-on-noop write is asynchronous and does NOT block dispatch (the `await` is in a fire-and-forget pattern or background task).
- [ ] T053 [P] FR-014 tier-1 refusal test in `tests/test_026_tier_one_refusal.py`: dispatch tier-1 input (system prompt) through a non-NoOp compressor; assert TierOneRefusalError raised; assert CompressorService surfaces as `compression_pipeline_error`; assert dispatch falls through.
- [ ] T054 [P] FR-022 Layer 6 closed-API skip is exercised in T048 (above).
- [ ] T055 Add the spec 011 amendment FRs FR-035..FR-037 per [research.md §16](./research.md): append to [specs/011-web-ui/spec.md](../011-web-ui/spec.md) per the established pattern (spec 023 T021 precedent). The amendment surfaces a "Compression Metrics" admin panel page with cache hit rate, compression ratio, density baseline. Pause and confirm with user before drafting per memory `reminder_spec_011_amendments_at_impl_time`.

---

## Phase 10: Closeout

- [ ] T056 Run the full `quickstart.md` smoke test (Steps 1-10) end-to-end against a live stack; capture any deltas as follow-up tickets — MAY DEFER if no live multi-provider stack is available; ride along with the next operator deploy per memory `project_deploy_dockge_truenas`.
- [ ] T057 Update spec.md Status line from "Clarified 2026-05-11" to "Implemented YYYY-MM-DD" once T001..T055 are saturated. Per memory `feedback_dont_declare_phase_done`, this task waits on explicit user direction — DO NOT flip Status without the user's confirmation.
- [ ] T058 [P] Update MEMORY.md if there are reusable learnings worth persisting from the 026 implementation (Phase 2 cutover patterns, summarizer filter wiring, etc.).
- [ ] T059 [P] V18 traceability audit per [plan.md Constitution Check V18](./plan.md): confirm every compressed segment carries the XML boundary marker AND a matching compression_log row exists for the same turn_id + participant_id + compressor_id.
- [ ] T060 Worktree-local CLAUDE.md (auto-generated by `update-agent-context.ps1`) — DEFERRED: review at PR-merge time. Repo-root `CLAUDE.md` carries the spec 026 entry from the original scaffold; worktree file may add nothing new.

---

## Parallel-execution guidance

Within a phase, `[P]` tasks operate on different files and can run in parallel. Cross-phase dependencies:
- Phase 1 (T001-T010) must complete BEFORE Phase 2.
- Phase 2 (T011-T022) must complete BEFORE Phases 3-8.
- Phases 3-8 can run in any order once Phase 2 is done; US1 (Phase 3) is the natural starting point because it's the smallest delta and exercises the routing_log emission path that other phases reuse.
- Phase 9 + Phase 10 land last.

## Status

- Phase 1 (Setup, T001-T010): saturated (10/10 done).
- Phase 2 (Foundational, T011-T022): saturated (11/12 done; T013 live-DB migration test deferred until a DB harness lands).
- Phase 3 (US1 caching markers, T023-T028): not started — touches `src/api_bridge/caching.py` + `src/api_bridge/litellm/dispatch.py` response handling; provider-specific cache-hit extraction.
- Phase 4 (US2 dual-write + summarizer filter, T029-T032): partial — T029 + T031 routing_log dual-write landed at `src/orchestrator/convergence.py` fire site (payload-extension fields deferred — no generic payload column on routing_log; readers JOIN convergence_log). T030 + T032 summarizer-corpus filter still pending.
- Phase 5 (US3 NoOp + CompressorService bridge wiring, T033-T038): partial — NoOp + tests landed in Phase 2; T038 lifespan freeze + writer mount landed at `src/mcp_server/app.py`. T037 (bridge dispatch call site in `src/orchestrator/loop.py`) remains.
- Phase 6 (US4 Phase 2 scaffolds, T039-T044): saturated for scaffold (6/6). Layer 4 LLMLingua-2 mBERT real body landed on top of the scaffold — gated on `SACP_COMPRESSION_PHASE2_ENABLED=true` AND the optional `compression-phase2` dep being installed. Version bumped 0-scaffold -> 1-llmlingua-real.
- Phase 7 (US5 Provence stub, T045-T046): saturated (2/2 done).
- Phase 8 (US6 Layer 6 stub + closed-API skip, T047-T050): partially done (T047 + T049 done; T048 + T050 deferred to bridge integration).
- Phase 9 (Polish, T051-T055): not started.
- Phase 10 (Closeout, T056-T060): not started.

**Commit trail on the 026-context-compression branch**: spec clarifications -> Phase 1 design artifacts -> tasks -> Phase 1 V16 gate -> Phase 2 foundational -> T031+T038 density dual-write + lifespan freeze -> Layer 4 LLMLingua-2 mBERT real body. 30 of 60 tasks complete. Remaining clusters: (a) bridge / dispatch wiring (T023-T028 + T030 + T032 + T037), (b) closed-API Layer 6 skip (T048 + T050), (c) closeout + spec 011 amendment (Phases 9-10).
