# API / Middleware Contract Requirements Quality Checklist: Network-Layer Per-IP Rate Limiting

**Purpose**: Validate that the spec's external-facing contract requirements (HTTP responses, header semantics, exempt-path matching, audit and metric shapes) are complete, unambiguous, and consistent. Tests the writing of the requirements, not the implementation.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md)

## HTTP 429 Response Contract

- [ ] CHK001 Is the HTTP 429 response status fixed for budget-exhaustion rejections, distinct from 400 for unresolvable IPs? [Clarity, Spec §FR-005 / FR-012]
- [ ] CHK002 Is the `Retry-After` header value semantic specified (RFC 6585 seconds-delta form, not HTTP-date)? [Clarity, Spec §Assumptions]
- [ ] CHK003 Is the response body content fixed and prohibited from echoing request content? [Completeness, Spec §FR-005]
- [ ] CHK004 Is the Retry-After value derived from the limiter's per-IP window-remaining state, with a deterministic computation rule? [Measurability, Spec §US1 AS3]

## HTTP 400 for Unresolvable Source IP

- [ ] CHK005 Is the unresolvable-IP case specified to reject (not pass through), with the failure mode explicitly fail-closed? [Clarity, Spec §FR-012]
- [ ] CHK006 Is the `source_ip_unresolvable` audit action specified with an explicit per-event (non-coalesced) emission rule, distinct from the rejection coalescing rule? [Clarity, Spec §FR-012]
- [ ] CHK007 Is the rejection counter increment specified with `exempt_match=false` for unresolvable-IP cases? [Consistency, Spec §FR-012]

## Exempt Path Matching

- [ ] CHK008 Is the exempt path match exact-path AND method-restricted (not prefix-match, not method-agnostic)? [Clarity, Spec §FR-006]
- [ ] CHK009 Is the exempt path list defined as a fixed module-level constant (not runtime-mutable), per C3 resolution? [Consistency, Spec §C3 resolution / Data Model §ExemptPathRegistry]
- [ ] CHK010 Is the OPTIONS preflight handling specified, or is it intentionally absent (subject to per-IP rate limit)? [Coverage, Gap]

## Forwarded Header Parsing

- [ ] CHK011 Is the parsing precedence specified (`Forwarded` per RFC 7239 preferred; `X-Forwarded-For` fallback)? [Completeness, Spec §FR-011]
- [ ] CHK012 Is "rightmost-trusted entry" defined precisely enough that two implementations would parse the same source IP from a multi-hop header? [Clarity, Spec §FR-011 / Gap]
- [ ] CHK013 Is operator responsibility for proxy hygiene (sanitizing upstream-supplied headers) specified rather than implied? [Completeness, Spec §FR-011 / Edge Cases]
- [ ] CHK014 Is the trust-by-opt-in default (`SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS=false`) consistent across the spec, validators, and contracts/env-vars.md? [Consistency, Spec §C1 resolution]

## WebSocket Upgrade Semantics

- [ ] CHK015 Is the WebSocket upgrade specified as a single network-layer event (counts at upgrade-time, not per-frame)? [Clarity, Spec §FR-015 / Edge Cases]
- [ ] CHK016 Is post-upgrade in-band traffic explicitly delegated to the §7.5 / spec 002 application-layer limiter, with no overlap? [Coverage, Spec §FR-015]

## Audit-Log Entry Shape

- [ ] CHK017 Are the `network_rate_limit_rejected` payload fields enumerated (source_ip_keyed, endpoint_path, method, rejected_at, limiter_window_remaining_s)? [Completeness, Spec §US3 AS1]
- [ ] CHK018 Is the `rejection_count` coalescing field defined with semantics (count over the (source_ip_keyed, minute) bucket)? [Clarity, Spec §FR-009]
- [ ] CHK019 Is the `source_ip_unresolvable` audit row's payload field set specified (and distinguished from the rejection row's)? [Completeness, contracts/audit-events.md]
- [ ] CHK020 Are the two new action strings added to the spec's `admin_audit_log` action taxonomy without colliding with existing strings? [Consistency, contracts/audit-events.md]

## Metric Label Cardinality

- [ ] CHK021 Are the `sacp_rate_limit_rejection_total` labels enumerated with their finite value sets (`endpoint_class={"network_per_ip", ...}`, `exempt_match={false, ...}`)? [Completeness, Spec §FR-010 / contracts/metrics.md]
- [ ] CHK022 Is the cardinality bound (number of label-value combinations across all current emitters) calculated and called out? [Measurability, contracts/metrics.md]
- [ ] CHK023 Is the cross-spec coordination with spec 016 explicit (this spec extends, does not redefine, the counter)? [Consistency, Spec §Cross-References]

## Middleware Ordering Contract

- [ ] CHK024 Is the "FIRST middleware" requirement specified with an enforcement mechanism (startup test asserting registration order)? [Measurability, Spec §FR-001 / FR-002 / contracts/middleware-ordering.md]
- [ ] CHK025 Is the FastAPI reverse-order semantics (last add = outermost = first to execute) called out, or is the ordering specified at the user-facing-execution level? [Clarity, contracts/middleware-ordering.md]
- [ ] CHK026 Are the carve-outs explicitly rejected ("no graceful-onboarding path", "no first-request-from-new-client path") and recorded in the spec? [Completeness, Spec §C2 resolution / FR-002]

## Configuration Contract

- [ ] CHK027 Are all five env vars (`_ENABLED`, `_RPM`, `_BURST`, `_TRUST_FORWARDED_HEADERS`, `_MAX_KEYS`) consistently named (prefix, casing, suffix conventions) across spec.md and contracts/env-vars.md? [Consistency]
- [ ] CHK028 Are the six standard fields (Default, Type, Valid range, Blast radius on invalid, Validation rule, Source spec(s)) populated for each env var in contracts/env-vars.md? [Completeness, contracts/env-vars.md]
- [ ] CHK029 Is the master-switch coupling specified (when `_ENABLED=true`, `_RPM` MUST be set; unset paired with `_ENABLED=true` exits at startup)? [Clarity, Spec §SACP_NETWORK_RATELIMIT_RPM]

## Notes

- The middleware-ordering startup test is the highest-impact contract canary; ensure CHK024 resolves to PASS before /speckit.tasks runs.
- Cross-spec metric and audit alignment (CHK020, CHK023) is verified by contracts/audit-events.md and contracts/metrics.md, not by spec.md alone.
