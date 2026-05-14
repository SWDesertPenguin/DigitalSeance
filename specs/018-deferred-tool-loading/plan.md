# Implementation Plan: Deferred Tool Loading for Large MCP Tool Sets

**Branch**: `018-deferred-tool-loading` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)

---

## Summary

Deferred tool loading is a partition mechanism layered above the per-participant MCP tool registry. The mechanism partitions each participant's tool set into a *loaded subset* (full definitions live in the per-turn dispatch payload) and a *deferred subset* (compact index entries the model sees in lieu of the full schema). Two SACP-orchestrator-provided discovery MCP tools (`tools.list_deferred`, `tools.load_deferred`) let the model exit the deferred state on demand. The deferred set is strictly per-participant and never leaks across participant boundaries.

This spec ships in two cuts within a single feature branch:

- **Phase-1 cut (US1)** ships **design hooks only**. The system-prompt assembly pipeline goes through the deferral-aware code path, consults a `DeferredToolIndex` interface that returns an empty set in v1, and emits the same dispatch payload as before. The two discovery MCP tools are registered as no-op stubs returning a documented `deferred_loading_disabled` response. The four V16 env vars + validators + doc sections land alongside. `SACP_TOOL_DEFER_ENABLED=false` is the default and produces byte-identical pre-feature behavior.
- **Phase-2 cut (US2 + US3)** ships the **working partition + discovery**. Once activated by `SACP_TOOL_DEFER_ENABLED=true`, the partition policy fills the loaded subset under `SACP_TOOL_LOADED_TOKEN_BUDGET` using registration-order selection, emits compact index entries for the deferred subset under `SACP_TOOL_DEFER_INDEX_MAX_TOKENS`, audits every partition decision and discovery-driven load to `admin_audit_log`, and coordinates with spec 017's freshness mechanism. The two discovery MCP tools become live (load returns the full definition + promotes the tool sticky-within-session).

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest, tiktoken (already a transitive dep via `src/api_bridge/tokenizer.py`). **No new runtime dependencies.** Phase 2 token counting reuses `src.api_bridge.tokenizer.get_tokenizer_for_participant` (existing module) — no new tokenizer libraries.
**Storage**: PostgreSQL 16. **No schema changes.** All audit entries (`tool_partition_decided`, `tool_loaded_on_demand`, `tool_re_deferred`) reuse the existing `admin_audit_log` table (spec 002 §FR-014). In-memory `DeferredToolIndex` per `(session_id, participant_id)` key — session-local, not persisted across restart (matches spec 015 and spec 017 stance).
**Testing**: pytest with `asyncio_mode = "auto"`. Phase-1 cut requires a regression contract: the full pre-feature acceptance suite MUST pass byte-identically. Phase-2 cut requires partition correctness + audit-log assertions + per-participant scoping verification + tokenizer-fallback warn-level assertion.
**Target Platform**: Linux server (Docker container per Constitution §6.8).
**Project Type**: Single backend project (Python orchestrator + FastAPI surface).
**Performance Goals**: Partition computation is `O(tools)` per participant per session start, well under the §4.2 line 446 "50ms per turn cycle" target. Discovery load is out-of-band from the turn loop. No per-partition LLM call (truncation-based summary generation is pure-Python).
**Constraints**: Per-participant scoping enforced at every boundary (system prompt, audit-log row, metric series). The Phase-1 cut MUST produce byte-identical pre-feature behavior. The Phase-2 cut MUST coordinate with spec 017 freshness without producing torn partition state (recomputation is serialized per participant).
**Scale/Scope**: 8-participant sessions per Constitution; per-participant tool counts up to ~50 expected; deferred index up to `SACP_TOOL_DEFER_INDEX_MAX_TOKENS` (default 256 tokens, ~30 tool entries).

## Source Code

```text
src/
├── orchestrator/
│   ├── deferred_tool_index.py        # Phase 1 + 2: DeferredToolIndex interface + partition logic
│   └── deferred_tool_audit.py        # Phase 2: audit-log helpers for the three action types
├── mcp_server/
│   └── tools/
│       └── deferred_tools.py         # Phase 1 + 2: tools.list_deferred + tools.load_deferred handlers
├── prompts/
│   └── tiers.py                      # Phase 1: assemble_prompt grows the optional deferred-index parameter
├── config/
│   └── validators.py                 # Phase 1: 4 new validators + uncomment reserved slots
└── orchestrator/
    └── context.py                    # Phase 1: build_full_context passes deferred-index hook through

docs/
└── env-vars.md                       # Phase 1: 4 new sections (six standard fields each)

tests/
├── test_018_phase1_hooks.py          # Phase 1: hook + stub + byte-identical regression
├── test_018_validators.py            # Phase 1: V16 validator unit tests
├── test_018_partition.py             # Phase 2: partition + recomputation + per-participant scoping
└── test_018_discovery.py             # Phase 2: tools.list_deferred + tools.load_deferred
```

## Constitution Check (V1-V19)

- **V1 (Sovereignty)**: PASS. Each participant's deferred set is part of their sovereignty surface (FR-006); no participant sees another's loaded/deferred partition, on-demand loads, or index contents. Facilitator visibility per §7.2 field model only.
- **V2 (Visibility into State)**: PASS. Every partition decision and discovery-driven load emits an `admin_audit_log` entry (FR-007, FR-008); operators can reconstruct capability changes from the audit log alone (SC-008).
- **V3 (Non-Repudiation)**: PASS. `admin_audit_log` is append-only per spec 002; nothing in this spec mutates audit rows.
- **V4 (Convergence-First)**: PASS. Deferred loading is independent of convergence detection; partition recomputation does not interact with convergence inputs.
- **V5 (Provider Adapter Abstraction)**: PASS. Phase-2 token counting reuses the existing `src/api_bridge/tokenizer.py` adapter resolution; no provider-specific code in the partition module.
- **V6 (Bridge-Layer Failure Isolation)**: PASS. Discovery tools are SACP-orchestrator-provided (not participant-MCP-server-provided), so MCP-server failures do not trip the spec 015 breaker via the discovery path.
- **V7 (Concurrency Discipline)**: PASS. Recomputation is serialized per participant via an `asyncio.Lock` on the `DeferredToolIndex` instance (FR-010 + research.md §4). No cross-participant lock; per-participant scoping prevents head-of-line blocking.
- **V8 (Resource Bounds)**: PASS. Loaded subset bounded by `SACP_TOOL_LOADED_TOKEN_BUDGET`; index bounded by `SACP_TOOL_DEFER_INDEX_MAX_TOKENS`; load timeout bounded by `SACP_TOOL_DEFER_LOAD_TIMEOUT_S`. Pathological partition (single tool > budget) graceful-degrades per Session 2026-05-13 clarification, not unbounded growth.
- **V9 (Time Budgets)**: PASS. Partition is `O(tools)` and runs once per session start + once per freshness refresh; well under the §4.2 50ms turn-prep target. Discovery load is out-of-band from the turn loop.
- **V10 (Test Schema Mirror)**: N/A. No schema changes; no migration; no conftest.py mirror update needed.
- **V11 (Audit Label Parity)**: PASS. Three new audit action types (`tool_partition_decided`, `tool_loaded_on_demand`, `tool_re_deferred`) added to the spec 002 catalog and the audit-label parity script's reference list.
- **V12 (Topology Applicability)**: PASS. Spec §V12 declares topologies 1-6 in scope; topology 7 (MCP-to-MCP) explicitly out of scope.
- **V13 (Use Case Coverage)**: PASS. All four use cases involving participants with multiple MCP servers covered (spec §V13).
- **V14 (Performance Budgets)**: PASS. Three budgets declared (partition at session start, recomputation on tool-set change, discovery load latency) — all bounded by existing budgets.
- **V15 (Failure Mode Documentation)**: PASS. Pathological-partition (single tool > budget) graceful-degradation is documented in spec edge cases + Session 2026-05-13 clarification; tokenizer-fallback fail-open is documented.
- **V16 (Configuration Gate)**: PASS. Four new env vars ship with validators + docs sections in lockstep before `/speckit.tasks` is run for the working-implementation cut — landed in the Phase-1 cut so the V16 gate is green from day one.
- **V17 (Per-Participant Isolation)**: PASS. FR-006 explicitly enforces; SC-004 contract-tests; no cross-participant state in `DeferredToolIndex`.
- **V18 (Traceability)**: PASS. Every FR-* and SC-* in spec.md maps to either an implementation file or a test (verified by `scripts/check_traceability.py` at closeout).
- **V19 (Documentation Deliverables)**: PASS. Four `docs/env-vars.md` sections + one `docs/admin-audit-log.md` row per new action type (verified by `scripts/check_doc_deliverables.py`).

## Project Structure

Single project, paths relative to repo root. Backend code in `src/`; tests in `tests/`. Documentation in `docs/`. Spec artifacts in `specs/018-deferred-tool-loading/`.

## Implementation Phases

### Phase 0 — Research

See [research.md](./research.md). Eleven research questions resolved during planning. Notable decisions: tokenizer reuses `get_tokenizer_for_participant`, partition lock is per-participant `asyncio.Lock`, audit emission uses existing `admin_audit_log` shape (no new columns), discovery tool naming follows spec 030 domain.action convention.

### Phase 1 — Design hooks (US1)

The Phase-1 cut ships the contract Phase 2 will fill. Five components land:

1. `src/orchestrator/deferred_tool_index.py` — `DeferredToolIndex` Protocol + `_EmptyIndex` no-op implementation + `get_deferred_index_for_participant(session_id, participant_id)` resolver returning the no-op in v1.
2. `src/orchestrator/context.py` — `build_full_context` accepts an optional `deferred_index` parameter, consults it once per turn-prep, and threads the result through to `assemble_prompt` (which itself accepts an optional `deferred_index_entries` parameter that defaults to None and emits nothing when empty).
3. `src/mcp_server/tools/deferred_tools.py` — `tools.list_deferred` + `tools.load_deferred` handlers registered against the existing SACP-native MCP surface, returning the documented stub `{"status": "deferred_loading_disabled", "spec": "018"}` when `SACP_TOOL_DEFER_ENABLED=false` (the v1 default).
4. `src/config/validators.py` — four new validators (`validate_sacp_tool_defer_enabled`, `validate_sacp_tool_loaded_token_budget`, `validate_sacp_tool_defer_index_max_tokens`, `validate_sacp_tool_defer_load_timeout_s`) appended to the `VALIDATORS` tuple in declaration order.
5. `docs/env-vars.md` — four new sections (six standard fields each) for the new env vars.

Tests:
- `tests/test_018_phase1_hooks.py` — asserts hook is consulted on every turn-prep; index returns empty set; discovery tools return stub; full pre-feature suite passes byte-identically (sample 5 representative tests).
- `tests/test_018_validators.py` — V16 validator unit tests per the existing pattern (`tests/test_015_validators.py` as reference).

### Phase 2 — Working partition + discovery (US2 + US3)

The Phase-2 cut fills in the contract Phase 1 shipped. Six components land:

1. `src/orchestrator/deferred_tool_index.py` — `DeferredToolIndex` gains real implementation: `compute_partition(tools, budget, tokenizer)` returns `(loaded[], deferred[])` using registration-order selection; `load_on_demand(tool_name)` promotes a deferred tool sticky-within-session; LRU eviction when promotion exceeds budget.
2. `src/orchestrator/deferred_tool_audit.py` — three audit-emission helpers: `emit_partition_decided`, `emit_loaded_on_demand`, `emit_re_deferred`. Each writes one `admin_audit_log` row with the FR-007/FR-008 payload shape.
3. `src/mcp_server/tools/deferred_tools.py` — `tools.list_deferred` returns the participant's index (paginated under `SACP_TOOL_DEFER_INDEX_MAX_TOKENS`); `tools.load_deferred(name)` validates ownership (caller's participant_id == participant_id of the deferred set), promotes, audits, and returns the full definition. Both reject cross-participant calls with `tool_not_in_caller_registry`.
4. `src/orchestrator/context.py` — `build_full_context` resolves a live `DeferredToolIndex` for the participant when `SACP_TOOL_DEFER_ENABLED=true`, runs the partition against the participant's tokenizer, and emits the loaded subset's full schemas + the deferred subset's compact index entries into the dispatch payload.
5. `src/orchestrator/tool_list_freshness.py` (existing on a separate branch — coordination point) — Phase-2 wires partition recomputation onto the freshness `tool_list_changed` event; `prompt_cache_invalidated` flag pairs between specs.
6. Tests: `tests/test_018_partition.py` (US2 acceptance scenarios), `tests/test_018_discovery.py` (US3 acceptance scenarios).

### Phase 3 — Closeout

Run the seven closeout preflight scripts; resolve any findings; flip spec status to "Implemented YYYY-MM-DD".

## Open Items / Deferred Concerns

- **Spec 017 coupling (Phase 2)**: the Phase-2 cut depends on spec 017's `ParticipantToolRegistry` and `tool_list_changed` audit event existing on main. As of 2026-05-13, spec 017 is on a local branch awaiting push. Phase-2 implementation work waits on spec 017 merging to main, OR cherry-picks the freshness-event signature into a coordination shim.
- **Spec 030 coupling (Phase 2)**: the discovery tool names follow the `domain.action` snake_case convention from spec 030's tool registry. As of 2026-05-13, spec 030's tool-registry implementation is on a local worktree awaiting push. Phase-2 implementation either registers against the current `src/mcp_server/tools/` surface (which uses a different naming pattern) OR waits for spec 030's tool registry to merge to main and registers via the new `ToolRegistry` interface.
- **Future-spec follow-up**: recency- and relevance-based selection policies are deferred to a future spec. The v1 registration-order policy is acceptable for the spec 018 ship; operators can re-evaluate after observing partition-decision audit logs.
