# Security Checklist: Spec 018 Deferred Tool Loading

**Branch**: `018-deferred-tool-loading` | **Date**: 2026-05-13

Status legend: `[PASS]` / `[PARTIAL]` / `[GAP]` / `[DRIFT]` / `[ACCEPTED]`

---

## Per-participant scoping (sovereignty enforcement)

- [ ] **S001** `tools.load_deferred` rejects cross-participant calls with `{"error": "tool_not_in_caller_registry"}` (US3 AS4). Verified by integration test asserting B's state unchanged after A-only-tool load attempt.
- [ ] **S002** `tools.list_deferred` returns ONLY the caller's deferred set; no leakage of another participant's tool names, summaries, or partition decisions. Verified by contract test running two-participant session and asserting B's response contains zero A tool names.
- [ ] **S003** `admin_audit_log` rows for partition decisions, on-demand loads, and re-deferrals all carry `participant_id` so the audit viewer can scope rendering per spec 029's filter contract. Verified by SQL query in quickstart and by audit-viewer unit test.
- [ ] **S004** `DeferredToolIndex` instances are keyed on `(session_id, participant_id)` -- no shared state across participants. Verified by per-participant test asserting two instances are distinct objects with independent `loaded_tools` lists.
- [ ] **S005** The `_LiveIndex` `asyncio.Lock` is per-instance (not per-session, not global). Verified by reading the implementation -- the lock is an instance attribute.

## Input validation

- [ ] **S006** `tools.load_deferred(name)` rejects names not in the caller's deferred set OR not in the caller's full tool registry (returns `tool_not_found`). Defends against name-injection probing.
- [ ] **S007** `SACP_TOOL_LOADED_TOKEN_BUDGET` rejects values outside `[512, 8192]` at startup. Defends against operator misconfiguration that would expose the orchestrator to arbitrary budget commitments.
- [ ] **S008** `SACP_TOOL_DEFER_INDEX_MAX_TOKENS` rejects values outside `[64, 1024]` at startup. Defends against pathological deferred-index sizes that would dominate the system prompt.
- [ ] **S009** `SACP_TOOL_DEFER_LOAD_TIMEOUT_S` rejects values outside `[1, 30]` at startup. Defends against operator-configured infinite-wait timeouts on the discovery path.
- [ ] **S010** `SACP_TOOL_DEFER_ENABLED` rejects unparseable values at startup (only `true`/`false` case-insensitive). Defends against ambiguous boolean interpretation.

## Confidentiality of tool definitions

- [ ] **S011** Tool definitions promoted via `tools.load_deferred` are returned ONLY to the calling participant. The audit log records the load occurred but does NOT include the tool's full schema body (only the name). Verified by inspecting the `tool_loaded_on_demand` payload shape in data-model.md.
- [ ] **S012** Tool summaries rendered into deferred-index entries reuse the existing public tool description -- no new disclosure surface. Verified by reading `render_index_entries`.
- [ ] **S013** Tool definitions in the loaded subset appear in the participant's own dispatch payload but NOT in any other participant's dispatch payload, audit-log row, or metric series. Verified by SC-004 contract test.

## Cache invalidation correctness

- [ ] **S014** A discovery-driven load (`tools.load_deferred`) emits exactly ONE prompt-cache invalidation per FR-009. Verified by audit-log assertion in US3 AS2 test.
- [ ] **S015** A spec-017 freshness refresh + a discovery-driven load arriving in close succession do NOT produce a torn partition state (FR-010 / edge case "concurrent partition recomputation"). Verified by a race-condition test exercising both paths with `asyncio.gather`.
- [ ] **S016** A discovery-driven load that triggers LRU eviction emits paired `tool_loaded_on_demand` + `tool_re_deferred` rows with matching `requested_at`/`re_deferred_at` timestamps. Verified by US3 AS3 test asserting the timestamp pairing.

## Pathological partition handling

- [ ] **S017** When a single tool's schema exceeds `SACP_TOOL_LOADED_TOKEN_BUDGET`, the orchestrator does NOT fail the session start; it graceful-degrades with `pathological_partition=true` audit flag (Session 2026-05-13 clarification). Verified by edge case test in US2 test file.
- [ ] **S018** The two discovery tools (`tools.list_deferred`, `tools.load_deferred`) are NEVER deferred -- they always appear in the loaded subset regardless of budget pathology (FR-011). Verified by `compute_partition` unit test.
- [ ] **S019** A participant whose model does not support native function calling has deferred loading disabled at registration (FR-012); the `[NEED:]` proxy path applies instead. No deferred-loading code paths execute for these participants. Verified by SC-007 registration test.

## Audit log completeness

- [ ] **S020** Every partition decision -- session start AND every recomputation -- emits one `tool_partition_decided` row with the full payload shape (loaded/deferred counts, names, token counts, policy, pathological flag, tokenizer info). Verified by SC-008 audit-completeness test.
- [ ] **S021** The three new audit action types appear in the audit-label parity reference (run `scripts/check_audit_label_parity.py` at closeout per T036).
- [ ] **S022** Audit emission is non-blocking on the partition / discovery hot paths (uses async-write pattern). Verified by reading `emit_*` helpers in deferred_tool_audit.py.

## V16 deliverable gate (FR-013)

- [ ] **S023** All four new env vars have validator functions registered in `VALIDATORS` (T002-T006). Verified by `python scripts/check_env_vars.py` at T011.
- [ ] **S024** All four new env vars have `docs/env-vars.md` sections with six standard fields (T007-T010). Verified by the same script.
- [ ] **S025** Validators exit at startup on out-of-range values; tested by T012's validator unit tests.

## Regression contract (Phase 1)

- [ ] **S026** With `SACP_TOOL_DEFER_ENABLED=false` (the v1 default), the full pre-feature acceptance suite passes byte-identically (SC-001). Verified by T018 US1 AS4 representative-sample regression test.
- [ ] **S027** Phase-1 hooks are additive and observable only via the deferred-tool index returning an empty set (FR-015). Verified by T018 US1 AS2 test asserting `is_empty() == True`.

## Forward-compat with spec 030

- [ ] **S028** Discovery tool handlers (`tools.list_deferred`, `tools.load_deferred`) accept `CallerContext`-shaped arguments so the migration to spec 030's `ToolRegistry` is a renamed-import refactor, not a contract change. Verified by reading the handler signatures.
- [ ] **S029** The tool names (`tools.list_deferred`, `tools.load_deferred`) match spec 030's `domain.action` snake_case convention so no rename is required when spec 030's tool registry lands.

## Operational safety

- [ ] **S030** Rollback is documented in quickstart.md: unset `SACP_TOOL_DEFER_ENABLED` + restart restores pre-feature behavior; in-flight sessions continue with current partition until next session start. No mid-flight repartition on env-var change.
- [ ] **S031** Tokenizer fallback (when no per-provider adapter exists) emits a WARN log and sets `tokenizer_fallback_used=true` in the audit payload so operators can investigate (Session 2026-05-13 clarification). Verified by T027 edge-case test.
- [ ] **S032** No new dependencies introduced in Phase 1 OR Phase 2 (per plan.md Technical Context). Verified by reading pyproject.toml diff in the cut PRs.
