# Cross-Spec Integration Quality Checklist: Network-Layer Per-IP Rate Limiting

**Purpose**: Validate that spec 019's cross-spec coordination contracts (with specs 002, 003, 015, 016, the Phase-2 Web UI on port 8751, the §7.5 application-layer limiter, Constitution §6.5 / §3, and Phase-2 forward references) are specified clearly, completely, and without coupling violations. This checklist tests integration-requirement quality, not the consumer specs' implementations.
**Created**: 2026-05-08
**Feature**: [spec.md §"Cross-References to Existing Specs and Design Docs"](../spec.md) + [data-model.md §"Cross-spec references"](../data-model.md)

## Spec 002 — MCP Server (Port 8750)

- [ ] CHK001 Is the cross-spec contract "the MCP server on port 8750 is the v1 surface protected by this middleware" specified as binding for the Phase 1 scope? [Completeness, Spec §"Cross-References" + Data-model §"Cross-spec references"]
- [ ] CHK002 Are the requirements for the limiter's interaction with spec 002's auth middleware specified — the limiter MUST run BEFORE spec 002's auth middleware sees the request? [Clarity, Contracts §middleware-ordering "Required pattern"]
- [ ] CHK003 Is the contract for credential-validation flow in topology 7 (where the MCP server may not be the participant-facing surface) specified — does spec 002's auth path still benefit from the limiter? [Gap, Research §8]
- [ ] CHK004 Are the requirements for the SSE-transport endpoint behavior specified — does an SSE long-lived connection count as one request at upgrade time, or per stream chunk? [Gap, Spec §"Edge Cases" "WebSocket upgrade request"]

## Spec 003 — Turn-Loop Engine (routing_log V14 Instrumentation)

- [ ] CHK005 Is the cross-spec contract "the limiter middleware's own duration surfaces through `routing_log` per spec 003 §FR-030" specified as binding? [Completeness, Spec §"Cross-References" + Plan §"Performance Goals"]
- [ ] CHK006 Are the requirements for the `routing_log` payload shape (`payload->>'middleware' = 'NetworkRateLimit'`, `payload->>'duration_ms'`) specified at sufficient detail to query consistently? [Clarity, Quickstart §"Watch routing_log middleware-duration sample"]
- [ ] CHK007 Is the rule "no new `routing_log.reason` enum values introduced by this spec" specified as binding to prevent reverse-coupling on spec 003? [Completeness, Data-model §"Cross-spec references"]
- [ ] CHK008 Are the requirements for sampling cadence on `routing_log` middleware-duration rows specified — every request, every Nth request, or operator-configurable? [Gap, Plan §"Performance Goals"]

## Spec 015 — Circuit Breaker

- [ ] CHK009 Is the cross-spec interaction with spec 015's circuit breaker specified — does a network-layer rejection feed any breaker state, or are the two paths fully isolated? [Gap, Plan §"Constitution Check"]
- [ ] CHK010 Are the requirements for the audit and metric paths specified — does spec 015's breaker observe the limiter's audit rows or counter, or are they independent? [Gap]

## Spec 016 — Prometheus Metrics

- [ ] CHK011 Is the cross-spec contract "this spec extends spec 016's existing counter `sacp_rate_limit_rejection_total` with two labels (`endpoint_class`, `exempt_match`)" specified as binding? [Completeness, Spec §FR-010 + Contracts §metrics]
- [ ] CHK012 Is the cardinality-bound contract specified — exactly one new time series for this spec (`endpoint_class="network_per_ip", exempt_match="false"`); total counter cardinality bounded above by `2 × 2 = 4`? [Completeness, Contracts §metrics "Cardinality bound"]
- [ ] CHK013 Are the requirements for spec 016's `/metrics` exempt-path coordination specified — `/metrics` is in this spec's exempt set per FR-006, and the exemption is byte-identical to spec 016's expectation that `/metrics` is unbounded? [Completeness, Spec §FR-006 + Spec 016 §FR-002]
- [ ] CHK014 Is the contract for `endpoint_class="app_layer_per_participant"` (reserved for §7.5's future adoption) specified explicitly enough to prevent this spec from emitting that value? [Clarity, Contracts §metrics "Future label values"]
- [ ] CHK015 Are the requirements for per-rejection counter increment vs per-coalesced-audit-row write specified at sufficient detail to verify both surfaces independently? [Completeness, Contracts §metrics "Increment semantics"]

## Constitution §6.5 — Bcrypt Auth (the Threat Model Anchor)

- [ ] CHK016 Is the rule "the limiter exists to close the bcrypt-CPU-DoS vector that Constitution §6.5 introduces by specifying bcrypt as the auth-token hash" specified as the load-bearing rationale? [Completeness, Spec §"Overview" + Plan §"Constitution Check V3"]
- [ ] CHK017 Are the requirements for "bcrypt MUST NOT run on rate-limited requests" specified as binding via the FR-001/FR-002 ordering contract? [Completeness, Spec §FR-002 + Contracts §middleware-ordering "Cross-spec references"]
- [ ] CHK018 Is the contract for measurement of "bcrypt invocation count stays bounded by RPM" specified at sufficient detail for SC-001's load test to verify? [Measurability, Spec §SC-001]

## Constitution §3 — Sovereignty Preservation

- [ ] CHK019 Is the rule "the network-layer limiter has no participant context, no ability to deduce participant identity from IP, and writes no participant state" specified as binding for sovereignty preservation? [Completeness, Plan §"Constitution Check V1" + Spec §"Cross-References"]
- [ ] CHK020 Are the requirements for keeping the limiter pre-auth (no participant identity at limiter time) specified at sufficient detail to reject any future code that introduces participant-aware keying? [Clarity, Spec §"Overview" + FR-007]
- [ ] CHK021 Is the contract "all five sovereignty guarantees preserved" verified per-guarantee in the spec/plan, not just asserted as a single check? [Verifiability, Plan §"Constitution Check V1"]

## §7.5 Application-Layer Limiter Non-Interaction Guarantee

- [ ] CHK022 Is the cross-spec contract "the network-layer limiter MUST NOT share state with, read state from, write state to, or otherwise interact with the §7.5 per-participant rate limiter" specified as binding (FR-007)? [Completeness, Spec §FR-007 + sacp-design.md §7.5]
- [ ] CHK023 Are the requirements for the SC-004 byte-identical contract test specified at sufficient detail (run the §7.5 acceptance suite with the network-layer limiter active; assert no behavior change)? [Measurability, Spec §SC-004]
- [ ] CHK024 Is the rule "a network-rejected request never updates per-participant state, never reaches the cost tracker, never touches conversation state, never updates audit-log entries other than `network_rate_limit_rejected`" specified as binding (SC-005)? [Completeness, Spec §SC-005 + FR-008]
- [ ] CHK025 Are the requirements for "both limiters MUST be independently testable" specified at sufficient detail to drive the test scaffolding? [Completeness, Spec §FR-007]
- [ ] CHK026 Is the architectural boundary "network-layer is per-IP pre-auth; application-layer is per-participant post-auth" specified consistently across spec, plan, and data-model? [Consistency, Spec §"Overview" + FR-007 + Plan §"Constitints"]

## Phase-2 Web UI on Port 8751 (Forward Reference)

- [ ] CHK027 Is the contract "the Phase-2 Web UI on port 8751 reuses this exact middleware via process-wide registration (not per-port); no spec amendment required" specified as binding? [Completeness, Spec §"Overview" + §"Assumptions"]
- [ ] CHK028 Are the requirements for the Phase-2 cut's optional default-RPM adjustment (browser-driven traffic patterns may warrant a different default; env var name stays the same) specified clearly enough to avoid spec drift? [Clarity, Spec §"Assumptions"]
- [ ] CHK029 Is the contract for the WebSocket upgrade boundary (counts as one request at upgrade; subsequent traffic over the established WebSocket is OUT OF SCOPE; handled by §7.5 / spec 002 application-layer limiter post-auth) specified consistently? [Consistency, Spec §FR-015 + §"Edge Cases"]

## Constitution §6.5 / Spec 011 (UI Forward-Reference)

- [ ] CHK030 Is the rule "spec 011 SPA is untouched (no UI surface in this spec)" specified explicitly, with no spec 011 amendment needed (per memory `reminder_spec_011_amendments_at_impl_time`)? [Clarity, Plan §"Summary" + Data-model §"Cross-spec references"]
- [ ] CHK031 Are the operator-facing surfaces of this spec (env vars, audit-log queries, metric labels, runbook entries) categorized as deployment surfaces, not user-facing UI? [Consistency, Spec §V13 + Plan §"Constitution Check V13"]

## Coupling Quality

- [ ] CHK032 Are the cross-spec coupling directions documented (this spec depends on spec 016's counter surface; this spec does NOT depend on spec 015 / spec 003 in any reverse way) — does any consumer spec inadvertently force a reverse dependency? [Verifiability]
- [ ] CHK033 Is the principle "this spec extends shared infrastructure (admin_audit_log, sacp_rate_limit_rejection_total, routing_log) without modifying their schemas or breaking their contracts" specified consistently across all touchpoints? [Consistency, Plan §"Storage" + Contracts §audit-events + Contracts §metrics]
- [ ] CHK034 Are the requirements for landing-order across the Phase-1-back-fill family (specs 015, 016, 017, 018, 019, 020) specified — does this spec block on any of them, or are they independent? [Gap]

## Cross-Spec Test Strategy

- [ ] CHK035 Are the requirements for cross-spec integration smoke tests specified at sufficient detail to verify post-deployment (`test_019_audit_and_metrics.py` covers spec 016 counter; `test_019_exempt_and_isolation.py` covers §7.5 non-interaction)? [Completeness, Plan §"Source Code" + Plan §"Notes for /speckit.tasks"]
- [ ] CHK036 Is the contract for spec 016's existing dashboards specified — adding two labels MUST NOT break existing dashboard queries; default-aggregation rules apply? [Gap, Contracts §metrics]
- [ ] CHK037 Are the requirements for the SC-004 §7.5 contract test specified at sufficient detail (run §7.5's acceptance suite under load; assert byte-identical behavior with the network-layer limiter active)? [Measurability, Spec §SC-004]

## Notes

Highest-impact open items:
- CHK009 + CHK010 ([Gap]) on spec 015 interaction — the spec does not currently say whether the breaker observes limiter-rejection state. If it should not, that should be specified as binding non-interaction.
- CHK022 + CHK024 are the load-bearing §7.5 non-interaction items; they support FR-007 / SC-004 / SC-005 — the architectural rule that distinguishes this spec from its siblings.
- CHK034 ([Gap]) on Phase-1-back-fill landing order — clarifying whether this spec gates on or is gated by 015/016/017/018/020 would unblock task-list scheduling.
- CHK036 ([Gap]) on spec 016 dashboard impact — adding two labels to an existing counter can break legacy queries that assume a single time series.

Use the `[PASS] / [PARTIAL] / [GAP] / [DRIFT] / [ACCEPTED]` annotation convention when triaging items.
