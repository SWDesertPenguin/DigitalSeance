---

description: "Task list for implementing spec 018 (deferred tool loading -- Phase 1 design hooks + Phase 2 working partition)"
---

# Tasks: Deferred Tool Loading for Large MCP Tool Sets

**Input**: Design documents from `/specs/018-deferred-tool-loading/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included -- spec defines three Independent Tests + 11 Acceptance Scenarios across US1-US3 (plus 8 Edge Cases), and plan.md enumerates test files per story. Tests land alongside implementation.

**Organization**: Tasks grouped by user story. Phase 2 covers shared infrastructure (V16 deliverable gate per spec FR-013). User-story phases follow. Phase-1 cut ships US1 only; Phase-2 cut ships US2 + US3.

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, OR independent functions in the same file with no shared edit point)
- **[Story]**: US1 / US2 / US3 (no label for Setup, Foundational, Polish)

## Path Conventions

Single project, paths under repo root. Backend code under [src/](src/); tests under [tests/](tests/) per [plan.md "Source Code"](specs/018-deferred-tool-loading/plan.md).

---

## Phase 1: Setup

**Purpose**: Branch hygiene + prerequisite verification.

- [X] T001 Verify working tree is on `018-deferred-tool-loading` branch and `python -m src.run_apps --validate-config-only` passes before any new validators land (confirms V16 baseline is green)

---

## Phase 2: Foundational (Blocking Prerequisites -- V16 Gate per FR-013)

**Purpose**: V16 env-var deliverables (4 validators + 4 doc sections). All user stories depend on these.

**CRITICAL**: No user-story task in Phase 3+ may begin until Phase 2 completes. The V16 gate is non-negotiable per spec FR-013.

### V16 deliverable gate (4 validators + 4 doc sections)

- [X] T002 [P] Add `validate_sacp_tool_defer_enabled` to [src/config/validators.py](src/config/validators.py): unset means `false` (return None); accepts `true`/`false` case-insensitive; any other value exits at startup. Source spec: 018 FR-013 / V16.
- [X] T003 [P] Add `validate_sacp_tool_loaded_token_budget` to [src/config/validators.py](src/config/validators.py): unset returns None (default applied at consumer); positive integer in `[512, 8192]`; out-of-range or non-integer exits at startup. Source spec: 018 FR-013.
- [X] T004 [P] Add `validate_sacp_tool_defer_index_max_tokens` to [src/config/validators.py](src/config/validators.py): unset returns None (default applied at consumer); positive integer in `[64, 1024]`; out-of-range exits at startup. Source spec: 018 FR-013.
- [X] T005 [P] Add `validate_sacp_tool_defer_load_timeout_s` to [src/config/validators.py](src/config/validators.py): unset returns None (consumer inherits MCP client request timeout); positive integer in `[1, 30]`; out-of-range exits at startup. Source spec: 018 FR-013.
- [X] T006 Append the four new validators to the `VALIDATORS` tuple at the bottom of [src/config/validators.py](src/config/validators.py) in declaration order: T002, T003, T004, T005. Depends on T002-T005.
- [X] T007 [P] Add `### SACP_TOOL_DEFER_ENABLED` section to [docs/env-vars.md](docs/env-vars.md) with six standard fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec).
- [X] T008 [P] Add `### SACP_TOOL_LOADED_TOKEN_BUDGET` section to [docs/env-vars.md](docs/env-vars.md) with six standard fields.
- [X] T009 [P] Add `### SACP_TOOL_DEFER_INDEX_MAX_TOKENS` section to [docs/env-vars.md](docs/env-vars.md) with six standard fields.
- [X] T010 [P] Add `### SACP_TOOL_DEFER_LOAD_TIMEOUT_S` section to [docs/env-vars.md](docs/env-vars.md) with six standard fields -- note unset = inherit MCP client request timeout.
- [X] T011 Run `python scripts/check_env_vars.py` from repo root and confirm V16 CI gate green for the four new vars (validators + doc sections in lockstep). Depends on T006-T010.
- [X] T012 [P] Validator unit tests in [tests/test_018_validators.py](tests/test_018_validators.py): each of the four validators -- valid value passes, out-of-range raises naming the offending var, unset returns None, boolean validator rejects garbage.

**Checkpoint**: V16 gate green. User-story phases unblocked.

---

## Phase 3: User Story 1 -- Phase 1 design hooks ship without behavior change (Priority: P1)

**Goal**: `DeferredToolIndex` Protocol + `_EmptyIndex` no-op + resolver + two MCP discovery tool stubs + assemble_prompt hook + byte-identical regression contract.

### DeferredToolIndex interface + no-op implementation

- [X] T013 [P] [US1] Create [src/orchestrator/deferred_tool_index.py](src/orchestrator/deferred_tool_index.py): define `DeferredToolIndex` Protocol per [contracts/deferred-tool-index.md](specs/018-deferred-tool-loading/contracts/deferred-tool-index.md) (read-side + mutation methods), `DeferredToolIndexEntry` frozen dataclass per [data-model.md](specs/018-deferred-tool-loading/data-model.md), and `_EmptyIndex` no-op implementation that satisfies the Protocol with zero state.
- [X] T014 [US1] Implement `get_deferred_index_for_participant(session_id, participant_id)` in [src/orchestrator/deferred_tool_index.py](src/orchestrator/deferred_tool_index.py): returns the process-scope-shared `_EmptyIndex` singleton when `SACP_TOOL_DEFER_ENABLED=false` (the v1 default). Depends on T013.

### Discovery MCP tool stubs

- [X] T015 [P] [US1] Create [src/mcp_server/tools/deferred_tools.py](src/mcp_server/tools/deferred_tools.py): register `tools.list_deferred` and `tools.load_deferred` handlers per [contracts/discovery-tools.md](specs/018-deferred-tool-loading/contracts/discovery-tools.md). Phase-1 stubs return `{"status": "deferred_loading_disabled", "spec": "018", "documentation": "..."}` per the contract. Wire into the existing SACP-native tool registration pattern (alongside facilitator.py / participant.py).

### assemble_prompt + build_full_context hooks

- [X] T016 [US1] Update [src/orchestrator/context.py](src/orchestrator/context.py) `build_full_context` (or the appropriate entry point that calls assemble_prompt for participants): resolve a `DeferredToolIndex` for the participant via `get_deferred_index_for_participant(session_id, participant_id)`; consult `is_empty()` and `render_index_entries()` once per turn-prep; thread the result through to `assemble_prompt`. Phase-1 behavior: index returns empty, no entries rendered, system prompt byte-identical to pre-feature baseline. Depends on T014.
- [X] T017 [US1] Update [src/prompts/tiers.py](src/prompts/tiers.py) `assemble_prompt`: add optional `deferred_index_entries: list[str] | None = None` parameter; when non-empty, append the entries as a new "Available deferred tools" Tier-4 fragment before canary insertion. Phase-1 behavior: parameter defaults to None so the prompt is byte-identical. Depends on T016.

### US1 tests

- [X] T018 [P] [US1] [tests/test_018_phase1_hooks.py](tests/test_018_phase1_hooks.py) -- US1 acceptance tests:
  - US1 AS1: 20-registered-tools participant with `SACP_TOOL_DEFER_ENABLED=false` -- system prompt contains the pre-feature baseline byte-identically (regression contract via snapshot test).
  - US1 AS2: `get_deferred_index_for_participant` returns an instance that satisfies the Protocol; `is_empty()` returns True; `loaded_tool_names()` returns `[]`; `deferred_tool_names()` returns `[]`; `render_index_entries(max_tokens=256)` returns `([], False)`.
  - US1 AS3: `tools.list_deferred` and `tools.load_deferred` invocations with `SACP_TOOL_DEFER_ENABLED=false` return the documented stub; no participant state mutates.
  - US1 AS4: representative pre-feature regression -- run 5 representative tests from the pre-feature suite (one each from session lifecycle, dispatch, audit log, convergence, security) and assert byte-identical outputs.

**Checkpoint**: Phase-1 cut (US1) ships. V16 gate green, design hooks in place, discovery tools stubbed, byte-identical regression contract verified. Phase-1 PR can land independently. Phase 2 (US2 + US3) follows in a separate cut once spec 017 freshness mechanism lands on main.

---

## Phase 4: User Story 2 -- Phase 2 partitioning keeps the system prompt within the budget (Priority: P2)

**Goal**: Working partition logic; registration-order policy; `tool_partition_decided` audit emission; spec-017 freshness coordination.

### Partition implementation

- [X] T019 [US2] Replace `_EmptyIndex` no-op with a working `_LiveIndex` class in [src/orchestrator/deferred_tool_index.py](src/orchestrator/deferred_tool_index.py): `compute_partition(tools, budget, tokenizer)` iterates tools in registration order, accumulates `tokenizer.count_tokens(t.full_schema)` into `loaded_token_count`, places tools in `loaded_tools` while the accumulator stays under `budget`, defers the rest. The two discovery tools (`tools.list_deferred`, `tools.load_deferred`) are always loaded regardless of budget (FR-011). Pathological case: if no real tool fits, `pathological_partition=True` and `loaded_tools` contains only the discovery tools. Depends on T014 (Phase 1 base in place).
- [X] T020 [US2] Implement `recompute_on_freshness(new_tools, budget, tokenizer)` in [src/orchestrator/deferred_tool_index.py](src/orchestrator/deferred_tool_index.py): merge promoted-and-still-present tools (preserve their loaded position), drop promoted-but-now-missing tools, then re-run partition over `new_tools` in registration order under `budget`. Acquires the per-`DeferredToolIndex` `asyncio.Lock` for the duration. Depends on T019.
- [X] T021 [US2] Implement `render_index_entries(max_tokens)` in [src/orchestrator/deferred_tool_index.py](src/orchestrator/deferred_tool_index.py): emit one-line strings per deferred tool in the format `- {name}: {summary} [load_via: tools.load_deferred(name="{name}")]`; truncate at `max_tokens` with a pagination banner. Depends on T019.

### Partition resolver activation

- [X] T022 [US2] Update `get_deferred_index_for_participant` in [src/orchestrator/deferred_tool_index.py](src/orchestrator/deferred_tool_index.py): when `SACP_TOOL_DEFER_ENABLED=true`, return a per-`(session_id, participant_id)` cached instance of `_LiveIndex`; when `false`, continue returning `_EmptyIndex`. Depends on T019.
- [X] T023 [US2] Wire partition execution into [src/orchestrator/context.py](src/orchestrator/context.py) `build_full_context`: when the resolved index is a `_LiveIndex` AND `is_empty()` returns True (first partition for this session), resolve the participant's tokenizer via `get_tokenizer_for_participant`, fetch the participant's tool list (from the freshness mechanism's `ParticipantToolRegistry` if available, else empty), and call `compute_partition`. Depends on T022.

### Audit emission

- [X] T024 [P] [US2] Create [src/orchestrator/deferred_tool_audit.py](src/orchestrator/deferred_tool_audit.py): three audit-emission helpers `emit_partition_decided(session_id, participant_id, index)`, `emit_loaded_on_demand(session_id, participant_id, tool_name, evicted_for)`, `emit_re_deferred(session_id, participant_id, tool_name, evicted_for_tool_name)`. Each writes one `admin_audit_log` row with the payload shape from [data-model.md](specs/018-deferred-tool-loading/data-model.md).
- [X] T025 [US2] Wire `emit_partition_decided` into `compute_partition` and `recompute_on_freshness` in [src/orchestrator/deferred_tool_index.py](src/orchestrator/deferred_tool_index.py). Depends on T024 and T020.

### Spec 017 freshness coordination

- [X] T026 [US2] Add `on_tool_list_changed(session_id, participant_id, new_tools)` hook in [src/orchestrator/deferred_tool_index.py](src/orchestrator/deferred_tool_index.py) that resolves the index and calls `recompute_on_freshness`. Phase-2 prerequisite: spec 017's freshness mechanism wires this hook into its `tool_list_changed` event emission (cross-spec coordination). If spec 017 is not on main when Phase 2 lands, this hook is callable but no production code calls it (test-only path). Depends on T020.

### US2 tests

- [X] T027 [P] [US2] [tests/test_018_partition.py](tests/test_018_partition.py) -- US2 acceptance tests:
  - US2 AS1: 20-tools-exceeding-budget participant with `SACP_TOOL_DEFER_ENABLED=true` and `SACP_TOOL_LOADED_TOKEN_BUDGET=1500` -- partition produces loaded subset summing under 1500 tokens; deferred subset contains the rest; total system prompt stays under budget.
  - US2 AS2: `tool_partition_decided` audit row emitted at first partition with all required payload fields.
  - US2 AS3: per-participant scoping -- participant A's partition does not affect participant B's index, system prompt, or audit-log rows.
  - US2 AS4: spec-017 freshness coordination -- calling `on_tool_list_changed` triggers recompute; new `tool_partition_decided` audited; prompt-cache prefix invalidates exactly once (test asserts the spec-017 `prompt_cache_invalidated=true` row is the single invalidation).
  - Edge: pathological partition (single tool > budget) -- `pathological_partition=true` in audit payload; loaded subset has only the two discovery tools.
  - Edge: tokenizer fallback -- a participant with no model-specific adapter triggers `_DefaultTokenizer` use; audit row sets `tokenizer_fallback_used=true`; WARN log emitted.

---

## Phase 5: User Story 3 -- Phase 2 discovery capability (Priority: P3)

**Goal**: `tools.load_deferred` promotes deferred tools; LRU eviction at budget; per-participant scoping enforcement; audit emission.

### load_on_demand implementation

- [X] T028 [US3] Implement `load_on_demand(tool_name, all_tools)` in [src/orchestrator/deferred_tool_index.py](src/orchestrator/deferred_tool_index.py): find the tool in `all_tools` (return None if not found); acquire the lock; check if promotion exceeds budget after accumulating the new tool's tokens; if exceeded, LRU-evict from `loaded_tools` (skipping the two discovery tools per FR-011) until the new tool fits; promote sticky-within-session (insert into `loaded_tools` at end of registration order). Returns the tool definition on success. Depends on T019.
- [X] T029 [US3] Wire `emit_loaded_on_demand` (and `emit_re_deferred` when an eviction occurred) into `load_on_demand`. Depends on T024 and T028.

### Discovery tool live handlers

- [X] T030 [US3] Update [src/mcp_server/tools/deferred_tools.py](src/mcp_server/tools/deferred_tools.py) `tools.list_deferred` handler: when `SACP_TOOL_DEFER_ENABLED=true`, resolve the caller's index, call `render_index_entries`, return `{deferred, truncated, next_page_token}`. Continue returning the stub when `SACP_TOOL_DEFER_ENABLED=false`. Depends on T021.
- [X] T031 [US3] Update [src/mcp_server/tools/deferred_tools.py](src/mcp_server/tools/deferred_tools.py) `tools.load_deferred` handler: when `SACP_TOOL_DEFER_ENABLED=true`, validate `ctx.participant_id == participant_id_of_deferred_set` (reject cross-participant with `{"error": "tool_not_in_caller_registry"}`); call `load_on_demand`; on success return `{tool, evicted_for_this}`; on tool-not-found return `{"error": "tool_not_found"}`; on timeout return `{"error": "load_timeout"}`. Continue returning the stub when `SACP_TOOL_DEFER_ENABLED=false`. Depends on T028.

### Cache invalidation coordination

- [X] T032 [US3] In `load_on_demand`, after successful promotion, invalidate the participant's prompt-cache prefix via the existing cache-invalidation hook (or emit a marker that the next turn-prep detects -- depends on cache implementation). Set `prompt_cache_invalidated=true` in the audit payload per FR-009. Depends on T028.

### US3 tests

- [X] T033 [P] [US3] [tests/test_018_discovery.py](tests/test_018_discovery.py) -- US3 acceptance tests:
  - US3 AS1: deferred tool T -- A's model invokes `tools.load_deferred(name="T")`; response contains T's full definition; T appears in A's loaded subset on next `is_loaded("T")` check.
  - US3 AS2: post-load -- A's next system-prompt assembly includes T's full schema; prompt-cache prefix invalidates exactly once; `tool_loaded_on_demand` audit row emitted with `prompt_cache_invalidated=true`.
  - US3 AS3: promotion exceeds budget -- LRU eviction occurs; `tool_re_deferred` audit row emitted with `evicted_for_tool_name=T`; promotion still succeeds (load takes priority over budget per FR-008).
  - US3 AS4: cross-participant rejection -- B invokes `tools.load_deferred("A_only_tool")`; response is `{"error": "tool_not_in_caller_registry"}`; A's state unchanged (zero new audit rows on A).

---

## Polish

- [X] T034 [P] FR-012 integration -- ACCEPTED DEFERRED. At participant registration time, models without native function-calling support should disable deferred loading (use `[NEED:]` proxy instead per §6.3). v1 deployment scope: every currently-supported model in the LiteLLM adapter supports native function calling, so the disabling code path would be a no-op today. Marker for the future spec that introduces a no-function-calling capability flag on `participants` -- at that point the integration test (registration -> audit row -> deferred loading bypassed) lands alongside the flag.
- [X] T035 V18 traceability: run `python scripts/check_traceability.py` and confirm all FR-* and SC-* labels in spec.md are referenced by at least one test or source file.
- [X] T036 Run all seven closeout preflights from repo root and fix any findings:
  - `python scripts/check_traceability.py`
  - `python scripts/check_doc_deliverables.py`
  - `python scripts/check_audit_label_parity.py`
  - `python scripts/check_detection_taxonomy_parity.py`
  - `python scripts/check_schema_mirror.py`
  - `python scripts/check_env_vars.py`
  - `python scripts/check_time_format_parity.py`
