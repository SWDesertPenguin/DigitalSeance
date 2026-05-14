# Security Checklist: Spec 017 — Tool-List Freshness

**Purpose**: Requirements quality review — tests whether the REQUIREMENTS are specific, testable, and complete. Does not evaluate the implementation.

**Scope**: isolation, audit completeness, privacy contract, failure handling, size cap, turn-prep boundary, push subscription safety, env var semantics, sovereignty.

**Status markers**: [PASS] [PARTIAL] [GAP] [DRIFT] [ACCEPTED]

---

## 1. Per-Participant Isolation (FR-006 / SC-003)

**CHK001** [PASS] FR-006 states that no participant's tool list, change events, or refresh state may appear in another participant's context, audit-log view, or metrics surface. The prohibition is explicit and covers three distinct surfaces (context, audit-log view, metrics). SC-003 backs it with a measurable contract test asserting zero cross-participant side effects across all four observables (cached registry, audit-log visibility, system-prompt content, metric surface). [Spec §FR-006, §SC-003]

**CHK002** [PASS] The registry key `(session_id, participant_id)` is specified in the Key Entities section and in data-model.md. The keying scheme is testable: any implementation that accidentally fans out a refresh to a different participant will fail SC-003's assertion that B's hash is unchanged. [Spec §Key Entities, data-model.md]

**CHK003** [PARTIAL] FR-006 grants the facilitator permission to view all participants' tool-set changes ("The facilitator MAY view all participants' tool-set changes per the §7.2 facilitator-visible field model"), but the spec does not define what "facilitator view" means in practice — no endpoint, query, or UI surface is specified for facilitator access. The permission grant is stated but the enforcement mechanism is unspecified, leaving an implementation gap for how facilitator read access is scoped versus participant read access. [Spec §FR-006]

**CHK004** [PASS] SC-003 specifies a concrete parallel-run contract test: participants A and B run concurrently, A's tool list churns, and the test asserts B's registry state, audit visibility, system-prompt content, and metric surface are unchanged. The "parallel" qualifier means the test exercises the race path, not just sequential updates. [Spec §SC-003]

**CHK005** [PARTIAL] The isolation requirement covers audit-log "view" (what the participant can see) but does not explicitly prohibit audit-log rows from carrying cross-participant information in the JSONB payload. The data-model.md shows that `target_id = participant_id` and the payload fields do not reference other participants — but this is an implementation decision, not a requirement. A requirement-level statement forbidding cross-participant references in the audit payload would close this gap. [Spec §FR-006, data-model.md]

---

## 2. Audit Completeness (FR-004)

**CHK006** [PASS] FR-004 enumerates all nine required audit fields: `session_id`, `participant_id`, `change_kind`, `tool_name`, `old_hash`, `new_hash`, `observed_at`, `trigger_source`, `prompt_cache_invalidated`. All nine are listed in a single requirement, making completeness verifiable without cross-referencing. [Spec §FR-004]

**CHK007** [PASS] All five `change_kind` values (`added`, `removed`, `description_changed`, `schema_changed`, `refresh_failed`) are enumerated in FR-004, cross-referenced in the Clarifications section (Session 2026-05-13 item 4), and each is covered by a distinct acceptance scenario or edge case. SC-007 explicitly contracts that each kind is driven and its audit entry asserted. [Spec §FR-004, §SC-007, Clarifications]

**CHK008** [PASS] `prompt_cache_invalidated` semantics are specified in two places: FR-012 (the field must be set true when the change invalidated the prompt-cache prefix) and Clarifications (the boolean is true when `last_refreshed_at` indicates the list was already dispatched at least once). Two-point specification enables cross-checking in implementation review. [Spec §FR-004, §FR-012, Clarifications §3]

**CHK009** [PARTIAL] FR-004 requires one audit entry per change event, and the contracts file specifies one row per `change_kind` per changed tool. However, the spec does not define the required audit cardinality for a refresh that adds two tools and removes one simultaneously — three rows or one? The contract file says "one row per `change_kind` detected in the diff," which implies three rows, but this cardinality rule lives only in the contract document, not in the spec's FR section. A reader relying on the spec alone would not know the row-count expectation. [Spec §FR-004, contracts/tool-refresh-contract.md]

**CHK010** [PASS] `trigger_source` domain is specified (`poll`, `push`, `manual`) in FR-004, and US3 acceptance scenario 4 adds `trigger_source="manual"` as a distinguishing requirement for operator-initiated refreshes. The `registration` value in data-model.md (not listed in FR-004's enum) is a minor inconsistency addressed separately in CHK016. [Spec §FR-004, §US3 acceptance scenario 4]

---

## 3. Privacy Contract (FR-004 / SC-007)

**CHK011** [PASS] Tool description text is designated participant-private in the spec Overview ("tool description text is treated as participant-private (§7.2) and never appears in cross-participant logs or metrics"), the Edge Cases section, and the Assumptions section ("Tool description text is treated as opaque participant-private content"). Three independent statements provide redundancy for auditors and implementors. [Spec §Overview, §Edge Cases, §Assumptions]

**CHK012** [PARTIAL] The spec prohibits tool description text from appearing "in cross-participant logs or metrics" but does not specify what happens when an operator queries the audit log directly — the `new_value` JSON payload is stored in `admin_audit_log` with `tool_name` (the tool's name, not description), but it is not explicit that the payload must never contain description text. The data-model confirms the payload shape does not include description text, but a spec-level prohibition would make this a testable requirement rather than an implicit design choice. [Spec §Edge Cases, data-model.md]

**CHK013** [PASS] The participant-private nature of the tool registry is specified with enough precision to implement and verify: the registry is keyed `(session_id, participant_id)`, is in-memory and not persisted, and the audit row carries `target_id = participant_id` without referencing other participants. These are implementable invariants. [Spec §Key Entities, data-model.md]

**CHK014** [GAP] There is no requirement prohibiting a participant from registering an MCP server URL that resolves to another participant's server (or a shared server). The privacy contract only addresses the orchestrator's handling of tool data after fetch; it does not address whether the MCP URL itself can be used to create cross-participant state leakage at the network layer. This is a sovereignty surface gap: a participant could register a URL pointing to another participant's MCP server and observe their tool-list behavior via the audit log. A requirement bounding acceptable MCP URL registration (e.g., URL uniqueness per session, or administrator-approved URL list) would close this. [Spec §FR-006, §Overview]

---

## 4. Failure Handling (FR-011)

**CHK015** [PASS] FR-011 specifies the three required properties of refresh failure: cached list preserved, failure audited with `change_kind=refresh_failed`, and next interval proceeds. All three are measurable: a test can inject a connection error and assert (a) the cached tool set is unchanged, (b) one `refresh_failed` audit row was written, and (c) a subsequent poll is not suppressed. [Spec §FR-011]

**CHK016** [PARTIAL] The retry mechanism in FR-011 is underspecified: "the next refresh interval MUST proceed" guarantees the poller resumes, but the spec does not bound how many consecutive failures are tolerated before escalation, nor does it specify whether the `consecutive_failures` counter (defined in data-model.md but not in any FR) has a threshold. The interaction with spec 015's breaker is deferred to a "MAY interact" clause without a quantitative trigger. The failure preservation guarantee is clear; the escalation path is not. [Spec §FR-011, data-model.md §ParticipantToolRegistry]

**CHK017** [PASS] Cache preservation on failure is stated unconditionally ("the cached list MUST be preserved") and is testable: inject a network error mid-refresh and assert `get_tools()` returns the pre-failure list and `tool_set_hash` is unchanged. The implementation's `_handle_fetch_error` path correctly does not modify `tools` or `tool_set_hash`, consistent with the requirement. [Spec §FR-011, src/orchestrator/tool_list_freshness.py]

---

## 5. Size Cap (FR-010)

**CHK018** [PASS] FR-010 specifies all three required overflow behaviors: truncate the list, emit an audit entry, and not crash. The "not crash" invariant is implied by the audit-and-continue semantics but is reinforced by V6 graceful degradation in the plan. The byte-counting method is specified in data-model.md via the `SACP_TOOL_LIST_MAX_BYTES` env var documentation and the env var section (`1024 <= value <= 1048576`). [Spec §FR-010, §Configuration]

**CHK019** [PARTIAL] The byte-counting method — specifically what is counted — is specified in the Configuration section as `SACP_TOOL_LIST_MAX_BYTES` bytes, but the spec does not say whether the cap applies to the raw JSON of the tools array, the serialized system-prompt contribution, or the UTF-8 encoding of the response body. The implementation uses `len(json.dumps(tools).encode())`, which is reasonable but is an implementation detail not mandated by the spec. A testable byte-counting method definition would make SC-002 ("system-prompt reflects new tool set byte-for-byte") auditable from the spec alone. [Spec §FR-010, §Configuration, src/orchestrator/tool_list_freshness.py]

**CHK020** [PARTIAL] The truncation behavior is "truncate to the first N tools that fit." The spec does not specify whether truncation is stable (always the same N tools for a given list) or deterministic across restarts. The implementation truncates greedily in response-order, which is deterministic for a given response but may vary if the server returns tools in different order. Since the hash is order-independent, a reordered truncated list could produce a different set than a previous truncated list, triggering a spurious change audit. A stability guarantee (e.g., "truncation MUST be applied after sorting by tool name") would prevent this. [Spec §FR-010, §Edge Cases]

---

## 6. Turn-Prep Boundary (FR-005)

**CHK021** [PASS] FR-005 specifies "NEXT turn-prep boundary (per §4.2 step 6)" and explicitly prohibits mid-payload rebuild. The Clarifications section (item 2) resolves the boundary: the hash check runs at `_assemble_and_dispatch` entry before `assembler.assemble(...)` is called. The two-point specification (FR-005 + Clarifications) gives implementors a clear contract and gives reviewers a testable assertion. [Spec §FR-005, Clarifications §2]

**CHK022** [PASS] Torn-read protection is specified: "The rebuild MUST NOT happen mid-payload assembly for a turn already in progress" (FR-005) and US2 acceptance scenario 3 requires the assembly to complete with whichever tool-set was sealed at step-6 start. The "sealed at step-6 start" formulation is precise enough to test: inject a concurrent refresh and assert the turn that started assembly uses the pre-refresh tool list while the next turn uses the post-refresh list. [Spec §FR-005, §US2 acceptance scenario 3]

**CHK023** [PARTIAL] The "NEXT turn" constraint is stated in FR-005 but Clarifications §2 immediately overrides it: "the assembler picks up the fresh tool list on this same turn (the system prompt is rebuilt on this turn, not deferred)." The FR and the clarification say opposite things about whether the current turn or the next turn sees the refreshed list. The clarification is authoritative (it resolves a named ambiguity), but the FR-005 text was not updated to match. A reader relying only on FR-005 would implement wrong behavior. [Spec §FR-005, Clarifications §2]

---

## 7. Push Subscription Safety (FR-007 / FR-008)

**CHK024** [PASS] FR-007 specifies the subscription attempt requirement and mandates auditing the subscription outcome, with three outcome states (`subscribed / not_supported / failed`) named in US3 acceptance scenario 1. The failure mode when push is not supported is specified in US3 acceptance scenario 2: fall back to polling-only, do not block registration. Both the positive and failure paths are specified. [Spec §FR-007, §US3]

**CHK025** [PASS] Phase 2 gating is clear: `SACP_TOOL_REFRESH_PUSH_ENABLED=false` is the Phase 1 default, the flag is specified in the Configuration section with its fail-closed semantics (unset = false), and FR-008/FR-009 are explicitly labeled "Phase 2." The stub-versus-full-delivery distinction is called out in Clarifications §1 and the Assumptions section. [Spec §FR-008, §FR-009, §Configuration, Clarifications §1]

**CHK026** [PARTIAL] FR-007 requires auditing the subscription outcome but does not specify what happens when the push subscription attempt itself times out versus when the server explicitly returns `not_supported`. The audit record would show `failed` in both cases, but the remediation differs (timeout may be transient; explicit not_supported is permanent). Distinguishing these in the audit payload would improve operator diagnostics. The ToolSubscriptionRecord in data-model.md has a `failure_reason` field that could carry this distinction, but FR-007 does not require it. [Spec §FR-007, data-model.md §ToolSubscriptionRecord]

---

## 8. Env Var Semantics (FR-013 / FR-014)

**CHK027** [PASS] FR-014 specifies the regression contract measurably: "tool lists captured once at registration, no polling, no audit events for freshness, no system-prompt rebuilds for tool changes (matches current behavior)" when all four env vars are unset. SC-005 backs this with a full pre-feature acceptance suite regression gate. The "unset = pre-feature behavior" contract is operationally testable. [Spec §FR-014, §SC-005]

**CHK028** [PASS] FR-014 specifies the invalid-value startup exit requirement, and SC-006 provides the measurable outcome: process exits with a clear message naming the offending var. FR-013 requires validators in `VALIDATORS` tuple before tasks run (V16 gate). The two requirements together form a complete fail-closed contract. [Spec §FR-013, §FR-014, §SC-006]

**CHK029** [PARTIAL] FR-014's "byte-identical" regression claim is strong but is not defined to include or exclude edge cases such as: a participant with a non-null `api_endpoint` where polling is disabled (does `register_participant` still run? does it still do the initial fetch?). The research.md §5 clarifies that `register_participant` is a no-op when `api_endpoint` is None, but when `api_endpoint` is non-null and the poll interval is unset, the initial fetch still runs. This means "byte-identical to pre-feature baseline" is only true for participants without MCP servers — participants with a registered MCP URL get an initial fetch they didn't get before. Whether this is intentional regression behavior should be stated explicitly. [Spec §FR-014, research.md §5]

---

## 9. Sovereignty (Constitution §3)

**CHK030** [PASS] The spec explicitly prohibits using one participant's tool list in another participant's context in three independent locations: FR-006 ("no participant's tool list … may appear in another participant's context"), the Overview ("other participants MUST NOT see another participant's tool catalogue, change events, or refresh state"), and the Cross-References section (Constitution §3 bounds FR-006). The prohibition covers the tool catalogue itself, change events, and refresh state — all three legs of the sovereignty surface. [Spec §FR-006, §Overview, §Cross-References]

---

## Summary

| Category | CHK IDs | [PASS] | [PARTIAL] | [GAP] |
|---|---|---|---|---|
| Per-participant isolation | CHK001-CHK005 | 3 | 2 | 0 |
| Audit completeness | CHK006-CHK010 | 4 | 1 | 0 |
| Privacy contract | CHK011-CHK014 | 2 | 1 | 1 |
| Failure handling | CHK015-CHK017 | 2 | 1 | 0 |
| Size cap | CHK018-CHK020 | 1 | 2 | 0 |
| Turn-prep boundary | CHK021-CHK023 | 2 | 1 | 0 |
| Push subscription safety | CHK024-CHK026 | 2 | 1 | 0 |
| Env var semantics | CHK027-CHK029 | 2 | 1 | 0 |
| Sovereignty | CHK030 | 1 | 0 | 0 |
| **Total** | **30** | **19** | **10** | **1** |

**Open items requiring spec attention** (in priority order):

- CHK023 [PARTIAL] — FR-005 text conflicts with Clarifications §2 on whether the current or next turn picks up the refreshed list. The clarification is authoritative but FR-005 should be corrected to say "on this same turn-prep boundary" rather than "on the affected participant's NEXT turn-prep boundary."
- CHK014 [GAP] — No requirement bounds MCP URL registration to prevent a participant from pointing their server URL at another participant's server. Cross-participant state leakage via MCP URL is unaddressed.
- CHK003 [PARTIAL] — Facilitator read-access to all participants' tool change events is granted by FR-006 but no mechanism (endpoint, query, UI) is specified for enforcing or testing the access boundary.
- CHK029 [PARTIAL] — FR-014's "byte-identical pre-feature behavior" claim does not hold for participants with a registered MCP URL even when polling is disabled (the initial fetch runs). Intentional or not, it should be stated.
