# Operations Quality Checklist: Network-Layer Per-IP Rate Limiting

**Purpose**: Validate that spec 019's operator-facing requirements (deployment workflow, runbook for tuning under flood, failure diagnostic queries, misconfiguration recovery, V14 monitoring, incident response, container/deployment hygiene, documentation completeness, Phase-2 forward path) are specified clearly enough for operators to apply during deployment, tuning, and incident response. This checklist tests operations-requirement quality, not the operational tooling.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [quickstart.md](../quickstart.md)

## Deployment Workflow

- [ ] CHK001 Are the requirements for first-deployment of the limiter specified (which env vars to set, how to verify the master switch took effect, what banner / log line to expect)? [Completeness, Quickstart §"Enable the limiter"]
- [ ] CHK002 Is the contract for the startup config-validation log line specified at sufficient detail (`"Config validation: 5 SACP_NETWORK_RATELIMIT_* validators passed"`)? [Clarity, Quickstart §"Enable the limiter"]
- [ ] CHK003 Are the requirements for the middleware-order log line specified (`"Middleware order (outermost first): NetworkRateLimit, ..."`) at sufficient detail to grep for in deployment? [Clarity, Quickstart §"Verify middleware registration order"]
- [ ] CHK004 Are the requirements for verifying the deployment specified (synthetic flood, Retry-After header check, audit-log query)? [Completeness, Quickstart §"Observe limiter behavior"]
- [ ] CHK005 Is the rollout sequence specified — can the limiter land in a single deployment, or does it need a phased rollout (e.g., test environment first, then production)? [Gap]

## Rollback to Pre-Feature Behavior

- [ ] CHK006 Are the operator paths for "rollback to pre-feature byte-identical behavior with all five vars unset (or `_ENABLED=false`)" specified at sufficient detail? [Completeness, Quickstart §"Disable the limiter"]
- [ ] CHK007 Is the contract "no `network_rate_limit_rejected` audit entries are emitted from the disable point forward" specified as binding for SC-006? [Clarity, Spec §SC-006 + Quickstart §"Disable the limiter"]
- [ ] CHK008 Are the requirements for "in-memory state does not survive restart" specified explicitly enough that operators understand existing per-IP buckets are reset on rollback? [Completeness, Quickstart §"Tune the limit"]
- [ ] CHK009 Is the rollback verification procedure specified — operator restarts, then confirms middleware is absent from the order log line? [Gap]

## Runbook for Tuning RPM/BURST Under Flood

- [ ] CHK010 Are the operator paths for "raise `_RPM`" specified at sufficient detail (file path to `.env`, restart procedure, post-restart verification)? [Completeness, Quickstart §"Tune the limit"]
- [ ] CHK011 Is the rule "raising RPM should typically raise BURST proportionally" specified at sufficient detail to avoid operator confusion (e.g., `BURST = RPM/4` heuristic)? [Clarity, Quickstart §"Tune the limit" + Contracts §env-vars `_BURST` "Note"]
- [ ] CHK012 Are the requirements for diagnosing "legitimate clients hitting 429 unexpectedly" specified (audit-log `rejection_count` per IP query)? [Completeness, Quickstart §"Troubleshooting"]
- [ ] CHK013 Is the contract for "many legitimate clients share an IP (NAT, corporate proxy)" specified — operator either raises RPM or enables `_TRUST_FORWARDED_HEADERS=true` after confirming proxy header sanitization? [Completeness, Quickstart §"Tune the limit" + Spec §"Edge Cases"]
- [ ] CHK014 Are the requirements for the per-shared-IP limitation specified explicitly enough to inform tuning decisions (known limitation of per-IP limiting; future amendments may introduce per-token / per-fingerprint layers)? [Completeness, Quickstart §"Tune the limit" + Spec §"Edge Cases"]

## Failure Diagnostic Queries

- [ ] CHK015 Are the SQL queries for `admin_audit_log` filtered by `network_rate_limit_rejected` specified clearly enough to run against any orchestrator deployment (no environment-specific variables)? [Clarity, Quickstart §"Audit-log query for rejection rows"]
- [ ] CHK016 Is the SQL query for `source_ip_unresolvable` rows specified at sufficient detail (filter by action, project `reason` / `request_path` / `request_method`)? [Completeness, Quickstart §"Audit-log query for rejection rows"]
- [ ] CHK017 Are the requirements for `routing_log` middleware-duration queries specified (`payload->>'middleware' = 'NetworkRateLimit'`)? [Clarity, Quickstart §"Watch routing_log middleware-duration sample"]
- [ ] CHK018 Is the operator path for verifying audit-log coalescing specified — sustained 1-hour flood from one IP produces 60 rows (one per minute), not thousands? [Completeness, Spec §SC-008 + Quickstart §"Audit-log query for rejection rows"]
- [ ] CHK019 Are the requirements for the metrics-surface query specified (Prometheus scrape, `sacp_rate_limit_rejection_total{endpoint_class="network_per_ip",exempt_match="false"}`) at sufficient detail to verify per-rejection durability? [Clarity, Quickstart §"Metrics surface"]

## Misconfiguration Recovery

- [ ] CHK020 Are the recovery paths for each documented startup failure mode specified (V16 validator failure with named offending var → operator reads error, fixes value, restarts)? [Completeness, Quickstart §"Enable the limiter" + Spec §SC-007]
- [ ] CHK021 Is the recovery path for "audit row missing despite metric increment" specified clearly enough for an operator to identify the root cause (background flush task crashed; metric counter remains accurate)? [Clarity, Quickstart §"Troubleshooting"]
- [ ] CHK022 Are the requirements for "spurious `source_ip_unresolvable` rows" recovery specified (proxy misconfiguration; inspect `reason` field; fix proxy)? [Completeness, Quickstart §"Troubleshooting"]
- [ ] CHK023 Is the recovery path for "high `routing_log` middleware-duration values" specified (raise `_MAX_KEYS` toward upper bound)? [Clarity, Quickstart §"Troubleshooting"]
- [ ] CHK024 Are the requirements for "test_019_middleware_order.py failure on a developer's branch" specified — operator (or developer) inspects `src/mcp_server/app.py::_add_middleware` registration order, fixes ordering? [Completeness, Quickstart §"Troubleshooting"]

## V14 Performance Monitoring

- [ ] CHK025 Are the V14 budget verification queries specified at sufficient detail (P50/P95/P99 percentile queries against `routing_log` middleware-duration rows)? [Completeness, Quickstart §"Watch routing_log middleware-duration sample"]
- [ ] CHK026 Is the contract for "limiter middleware overhead is constant-time `O(1)`" specified with a numeric threshold or a cross-reference to where it's defined (V14 per-stage budget tolerance)? [Clarity, Spec §"Performance Budgets"]
- [ ] CHK027 Are the requirements for "per-IP-budget eviction is `O(1)` amortized" specified with the LRU mechanism (`OrderedDict.popitem(last=False)`) named and the duration captured? [Measurability, Spec §"Performance Budgets" + Research §3]
- [ ] CHK028 Is the contract "audit-log coalescing flush MUST run on a background timer, NOT in the request path" specified with the V14 budget enforcement mechanism (flush is asynchronous and MUST NOT block any request)? [Clarity, Spec §"Performance Budgets"]
- [ ] CHK029 Is the operator path for "V14 budget violation detected" specified — what runbook to follow, who to escalate to? [Gap]

## Incident Response — Active Flood Mitigation

- [ ] CHK030 Are the requirements for "active flood detected via metrics dashboard" incident response specified (immediate operator action: lower RPM via env-var change + restart, or block at upstream proxy)? [Gap, Quickstart §"Tune the limit"]
- [ ] CHK031 Is the contract for "use the audit log to identify flooding source IPs" specified at sufficient detail (filter by `network_rate_limit_rejected`, group by `target_id`, sort by `rejection_count` sum)? [Completeness, Spec §US3 + Quickstart §"Audit-log query for rejection rows"]
- [ ] CHK032 Are the requirements for "the audit log carries forensic value across orchestrator restarts" specified — the metrics counter survives via Prometheus scrape; the audit log persists durable per-(IP, minute) records? [Completeness, Research §6 + Spec §SC-008]
- [ ] CHK033 Is the contract for "what the limiter is NOT designed to defend against" specified (saturating exempt paths via misconfigured monitoring; defense at load-balancer layer if needed)? [Clarity, Spec §"Edge Cases" "Health/metrics scrape from a misconfigured monitoring system"]

## Container and Deployment Hygiene

- [ ] CHK034 Are the requirements for memory bound under flood specified — `MAX_KEYS × ~300 bytes per entry` ≈ 30MB worst case at the 100k default? [Completeness, Data-model §"PerIPBudget" "Memory bound" + Research §3]
- [ ] CHK035 Is the contract for the multi-worker FastAPI limitation specified — each worker has its own per-IP budget map; per-worker per-IP keying boundary documented? [Completeness, Data-model §"PerIPBudget" "Concurrency"]
- [ ] CHK036 Are the requirements for env-var change → restart specified (no live-reload; env-var changes require restart)? [Completeness, Quickstart §"Tune the limit" + Spec §FR-014]
- [ ] CHK037 Is the contract for "in-memory state does not survive restart by design" specified consistently across spec, plan, and quickstart? [Consistency, Quickstart §"Tune the limit" + Data-model §"PerIPBudget"]

## Documentation Completeness

- [ ] CHK038 Is the runbook for limiter operations integrated with existing operational docs (where does this content live; how is it discovered)? [Gap]
- [ ] CHK039 Are the requirements for the troubleshooting table's coverage specified (six documented symptoms in quickstart §"Troubleshooting" — is this set complete)? [Completeness, Quickstart §"Troubleshooting"]
- [ ] CHK040 Is the contract for operator-facing changelog of limiter behaviors specified — how operators learn about future RPM-default changes or label additions? [Gap]

## Phase-2 Forward Path

- [ ] CHK041 Is the operator-facing path for "Phase-2 Web UI on port 8751 reuses this middleware" specified at sufficient detail (no new env vars; same `_ENABLED` master switch covers both ports; default RPM may be tuned)? [Completeness, Spec §"Assumptions"]
- [ ] CHK042 Are the requirements for "browser-driven traffic patterns may warrant a different default RPM" specified clearly enough to inform the Phase-2 cut without amendment to this spec? [Clarity, Spec §"Assumptions"]
- [ ] CHK043 Is the contract for "no separate Phase-2 spec; the Phase-2 wiring is described in this spec's assumptions" specified consistently to prevent spec drift later? [Consistency, Spec §"Assumptions" + Plan §"Scale/Scope"]

## Notes

Highest-impact open items:
- CHK029 ([Gap]) on V14 budget violation runbook — without this, an operator seeing high `routing_log` middleware-duration values has no escalation path.
- CHK030 ([Gap]) on active-flood incident response — the spec lists the surfaces (audit, metrics) but not the operator's playbook (what to lower RPM to, how fast to act).
- CHK038 + CHK040 ([Gap]) on documentation discoverability and changelog — the runbook content lives in quickstart.md; whether that gets surfaced into a top-level operator doc is unspecified.
- CHK009 ([Gap]) on rollback verification procedure — beyond the disable-then-restart path, the spec does not specify the "did rollback actually take effect" check.

Use the `[PASS] / [PARTIAL] / [GAP] / [DRIFT] / [ACCEPTED]` annotation convention when triaging items.
