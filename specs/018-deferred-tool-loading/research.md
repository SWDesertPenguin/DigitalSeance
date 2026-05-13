# Research: Deferred Tool Loading

**Branch**: `018-deferred-tool-loading` | **Date**: 2026-05-13 | **Plan**: [plan.md](./plan.md)

---

## 1. Token counting at partition time

**Decision**: Reuse `src.api_bridge.tokenizer.get_tokenizer_for_participant` — the per-participant tokenizer adapter that already serves budget enforcement elsewhere in the codebase.

**Rationale**: The tokenizer adapter is the canonical "what does THIS participant's model count as a token" answer. It dispatches to OpenAI tiktoken (cl100k/o200k), Anthropic fallback (cl100k × 1.10), Gemini fallback (cl100k × 0.95), or a default cl100k estimator when no provider-specific path applies. Spec 018 partition decisions MUST use the same tokenizer the dispatch budget uses; otherwise partition decisions undercount or overcount relative to what the model actually consumes.

**Fallback**: When `get_tokenizer_for_participant` returns the `_DefaultTokenizer` (participant has no model-specific adapter), the partition module logs a WARN-level message and proceeds with the default estimator. Per Session 2026-05-13 clarification, the orchestrator does not fail-closed on tokenizer fallback — the deferral mechanism graceful-degrades to a coarse estimate.

**Alternatives considered**: (a) `len(s) // 4` rough cut — rejected because the existing codebase has moved past this estimate (commit history shows tokenizer.py replaces the rough cut for budget decisions); (b) per-tool-definition LLM-based summarization (would change the token cost) — rejected because the spec assumption is truncation-based summaries, not LLM-generated ones (no per-partition LLM cost on hot path).

## 2. Audit-log row shape

**Decision**: All three new action types (`tool_partition_decided`, `tool_loaded_on_demand`, `tool_re_deferred`) reuse the existing `admin_audit_log` table shape from spec 002 §FR-014. No new columns, no migration. The action-specific payload lives in the existing `payload` JSON column.

**Rationale**: The admin_audit_log table already carries `session_id`, `participant_id`, `action_type`, `payload`, `timestamp`. Three new action_type strings are additive — no schema change is needed and the existing audit viewer (spec 029) renders them automatically once they land in the catalog. Cross-spec audit-label parity (per `scripts/check_audit_label_parity.py`) verifies the three labels appear in both the spec.md and the implementation.

**Payload shapes**:
- `tool_partition_decided`: `{loaded_count, deferred_count, loaded_token_count, decided_at, selection_policy, pathological_partition, tokenizer_name, tokenizer_fallback_used}`.
- `tool_loaded_on_demand`: `{tool_name, requested_at, prompt_cache_invalidated, evicted_tool_name (nullable)}`.
- `tool_re_deferred`: `{tool_name, re_deferred_at, reason="lru_eviction_after_load", evicted_for_tool_name}`.

## 3. Per-participant locking strategy

**Decision**: One `asyncio.Lock` per `DeferredToolIndex` instance. The partition recomputation path (`compute_partition`) and the discovery-load path (`load_on_demand`) both acquire the lock for the duration of the mutation.

**Rationale**: Spec FR-010 and edge case "concurrent partition recomputation" require that a spec-017 freshness refresh and a discovery-driven load arriving in close succession not produce a torn partition state. Per-participant locking (not session-global or process-global) prevents head-of-line blocking — participant A's partition recompute does not stall participant B's discovery load.

**Why not a single global lock**: would serialize partition activity across all participants in all sessions; defeats the per-participant isolation requirement (FR-006).

**Why not optimistic concurrency**: the partition data structure is small (one list of loaded tools + one list of deferred entries) and the mutation rate is low (one partition decision per session start + one per freshness refresh + one per discovery load). The simplicity of `asyncio.Lock` outweighs the marginal throughput gain of CAS-style optimistic updates.

## 4. Selection policy for v1

**Decision**: Registration order. Tools land in the participant's registry in the order spec 017's freshness mechanism delivers them; partition selects the first N that fit `SACP_TOOL_LOADED_TOKEN_BUDGET`.

**Rationale**: Deterministic, no embedding cost on hot path, no LLM call, no semantic-similarity computation. Operators can reason about partition outcomes by inspecting the participant's tool list — first tools fit, later tools defer.

**Alternatives deferred to future spec**: (a) recency-based (loaded subset = N most-recently-used tools in this session) — requires use-tracking state and recency-aware partition recomputation on every tool call; (b) relevance-based (semantic match between conversation topic and tool description) — requires embedding pre-computation per tool and per-turn similarity recompute. Both are complex enough to defer to a separate spec once operators have observed v1 behavior.

## 5. Sticky-within-session promotion

**Decision**: A successful `tools.load_deferred` call promotes the tool into the loaded subset for the remainder of the session. The promotion does not persist across session restart; on restart the partition recomputes with the registration-order policy from scratch.

**Rationale**: Session-local matches the broader project stance (spec 015 and spec 017 both use session-local in-memory state). Persistence would require a new table and complicate session-restart semantics ("does the orchestrator honor old promotions that were appropriate for a now-stale tool set?").

**Behavior on subsequent freshness refresh**: when spec 017's freshness mechanism delivers a new tool list, the partition recomputes from the new list. Promoted tools that still exist in the new list remain promoted; promoted tools that disappeared are dropped from both subsets. The recomputation emits a fresh `tool_partition_decided` audit entry.

## 6. Discovery tool naming

**Decision**: `tools.list_deferred` and `tools.load_deferred` (domain.action snake_case, matching spec 030 tool-registry convention).

**Rationale**: Spec 030's tool registry has settled on `domain.action` snake_case across all 10 tool categories. The two discovery tools sit in the `tools.*` domain, alongside any future tool-management primitives. Naming consistency lets clients discover all tool-management capabilities via a single registry prefix.

**Caller scope**: participant-callable on their own deferred set only (FR-006). The dispatcher MUST verify `ctx.participant_id == request.participant_id` and reject cross-participant calls with `{"error": "tool_not_in_caller_registry"}` per US3 AS4. The facilitator can call them on any participant's set via the §7.2 facilitator-visible field model — but the v1 cut does not expose a facilitator override path; this is a future-spec extension.

## 7. Pathological partition (single tool > budget)

**Decision**: Graceful degradation. The loaded subset may contain only the two discovery tools (or be empty if discovery is not yet registered, which is not a real state). All participant tools are deferred. The `tool_partition_decided` audit entry sets `pathological_partition=true` so operators see this state in the audit log.

**Rationale**: Failing the session start on a budget pathology would be worse than degrading — the operator has chosen the budget, the participant has chosen the tools. The model still has a path forward (use discovery to load tools as needed); operators see the pathology in the audit log and can adjust the budget OR re-scope the participant's tool set.

## 8. Index entry shape

**Decision**: Compact entry = `{"name": str, "summary": str, "load_via": "tools.load_deferred(name=...)"}` rendered as one line per tool. The summary is the first ~80 chars of the tool's description, truncated at a word boundary.

**Rationale**: Each entry ~12-15 tokens. At 256 tokens of index budget (default), ~20 deferred tools fit before truncation. Pagination via `tools.list_deferred` is the safety valve when the participant has more deferred tools than fit the index budget.

**No schema, no examples**: by design — the model already has the full schema indirectly via `tools.load_deferred`. The index is a directory, not a documentation page.

## 9. V16 env-var mapping

Four new env vars, all consumed in `src/orchestrator/deferred_tool_index.py` and `src/orchestrator/context.py`. Each gets a validator function in `src/config/validators.py` and a `### SACP_TOOL_DEFER_*` section in `docs/env-vars.md` with the six standard fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec).

| Env Var                              | Type        | Default     | Range            | Validator                                          |
|--------------------------------------|-------------|-------------|------------------|----------------------------------------------------|
| `SACP_TOOL_DEFER_ENABLED`            | boolean     | `false`     | true/false       | `validate_sacp_tool_defer_enabled`                 |
| `SACP_TOOL_LOADED_TOKEN_BUDGET`      | positive int| `1500`      | [512, 8192]      | `validate_sacp_tool_loaded_token_budget`           |
| `SACP_TOOL_DEFER_INDEX_MAX_TOKENS`   | positive int| `256`       | [64, 1024]       | `validate_sacp_tool_defer_index_max_tokens`        |
| `SACP_TOOL_DEFER_LOAD_TIMEOUT_S`     | positive int| (inherits)  | [1, 30]          | `validate_sacp_tool_defer_load_timeout_s`          |

`SACP_TOOL_DEFER_LOAD_TIMEOUT_S` unset inherits the MCP client request timeout (currently 30s; future-proof for Phase-3 timeout refactor).

## 10. Coordination with spec 017 freshness

**Decision**: Phase 1 ships the design hook (the partition module exposes a `recompute_on_freshness(session_id, participant_id)` no-op stub). Phase 2 wires the stub to the live partition when spec 017's `tool_list_changed` event fires.

**Rationale**: Phase 1 lands on main today (no spec 017 dependency); Phase 2 lands after spec 017 merges to main. The hook contract is the integration boundary.

**Cache invalidation semantics**: A spec-017 refresh causes ONE prompt-cache invalidation (spec 017 already emits `prompt_cache_invalidated=true`). The spec-018 partition recomputation does NOT emit a separate invalidation — it shares the spec-017 invalidation. The audit log shows two rows (`tool_list_changed` from spec 017, then `tool_partition_decided` from spec 018) tied by `session_id + participant_id + timestamp` proximity. A discovery-driven load (`tools.load_deferred`) DOES emit its own invalidation, per FR-009 — this is the "load is a single invalidation event" rule.

## 11. Discovery-tool registration against current SACP MCP surface

**Decision**: Phase 1 registers the two discovery tools in `src/mcp_server/tools/deferred_tools.py` using the existing SACP-native tool registration pattern (alongside `src/mcp_server/tools/facilitator.py` and `src/mcp_server/tools/participant.py`).

**Rationale**: Spec 030's `ToolRegistry` with `domain.action` naming is not yet on main as of 2026-05-13. The Phase-1 cut registers the discovery tools against the current surface so the V16 gate is observable today; the Phase-2 cut OR a follow-up rename PR migrates them onto spec 030's `ToolRegistry` once that merges.

**Forward-compatibility hook**: the handler functions in `deferred_tools.py` are written to be wire-compatible with spec 030's `ToolDispatch` signature (i.e., they accept `CallerContext`-shaped arguments even if the current surface uses a different argument convention). This minimizes the migration work when spec 030's tool registry lands.
