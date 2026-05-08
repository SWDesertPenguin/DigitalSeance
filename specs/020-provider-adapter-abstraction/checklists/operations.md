# Operations Quality Checklist: Pluggable Provider Adapter Abstraction

**Purpose**: Validate that spec 020's operational requirements (deployment, runbook, recovery, monitoring, rollback) are specified clearly enough for operators to apply during deployment and incident response. This checklist tests operations-requirement quality, not the operational tooling.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [quickstart.md](../quickstart.md)

## Deployment Workflow

- [ ] CHK001 Are the requirements for first-deployment of the adapter abstraction specified (what changes operators see; what env vars they don't need to set; what banner to expect)? [Completeness, Quickstart §1]
- [ ] CHK002 Is the contract for the startup banner specified at sufficient detail (line format, info content, log destination)? [Clarity, Tasks §T043 + Quickstart §1]
- [ ] CHK003 Are the requirements for verifying the deployment specified (what test to run, what query confirms success)? [Completeness, Quickstart §1 + §2]
- [ ] CHK004 Is the rollout sequence specified — can the adapter abstraction land in a single deployment, or does it need a phased rollout? [Gap]

## Runbook for Switching Adapters

- [ ] CHK005 Are the operator paths for "switch to mock adapter for staging" specified at sufficient detail (file path conventions, env var names, restart procedure)? [Completeness, Quickstart §3]
- [ ] CHK006 Are the requirements for fixture-file deployment specified (where to place it, what permissions, what container volume mounts)? [Clarity, Quickstart §3]
- [ ] CHK007 Is the verification procedure for "mock adapter active and no network egress" specified (banner check + tcpdump or equivalent)? [Completeness, Quickstart §3]
- [ ] CHK008 Are the requirements for rollback to LiteLLM specified at sufficient detail (unset env vars, restart, verify banner)? [Completeness, Quickstart §3]

## Failure Diagnostic Queries

- [ ] CHK009 Are the SQL queries for diagnosing adapter behavior specified clearly enough to run against any orchestrator deployment (no environment-specific variables)? [Clarity, Quickstart §5]
- [ ] CHK010 Are the requirements for `routing_log` columns specified (`adapter_name`, `original_exception_class`, `normalize_error_category`, `retry_after_seconds`, `provider_family`)? [Completeness, Quickstart §5]
- [ ] CHK011 Is the operator path for verifying canonical-error mapping specified — operator runs query, compares to mapping table, files PR if drift detected? [Completeness, Quickstart §5]
- [ ] CHK012 Are the requirements for the `provider_family` enum verification query specified (which values are expected, which indicate a bug)? [Clarity, Quickstart §5]

## Misconfiguration Recovery

- [ ] CHK013 Are the recovery paths for each documented startup failure mode specified (8 modes in quickstart §6)? [Completeness, Quickstart §6]
- [ ] CHK014 Is the recovery path for "MockFixtureMissing on every dispatch" specified clearly enough for an operator to identify the root cause (canonical hash + last-message substring → which fixture to add)? [Clarity, Quickstart §6]
- [ ] CHK015 Are the requirements for "Adapter not initialized" recovery specified (code regression path; file a bug)? [Completeness, Quickstart §6]
- [ ] CHK016 Is the recovery path for "topology 7 has no bridge layer" error specified (code regression; file a bug — not an operator-fixable misconfiguration)? [Clarity, Quickstart §6]

## V14 Performance Monitoring

- [ ] CHK017 Are the V14 budget verification queries specified at sufficient detail (P50/P95/P99 percentile queries, comparison to historical baseline)? [Completeness, Quickstart §7]
- [ ] CHK018 Is the contract for "delta MUST fit within V14 per-stage budget tolerance" specified with a numeric threshold or a cross-reference to where it's defined? [Clarity, Spec §"Performance Budgets"]
- [ ] CHK019 Are the requirements for `normalize_error()` constant-time verification specified (single-digit microseconds at p99, threshold for alerting)? [Measurability, Quickstart §7]
- [ ] CHK020 Is the operator path for "V14 budget violation detected" specified — what runbook do they follow, who do they escalate to? [Gap]

## Cross-Spec Verification

- [ ] CHK021 Are the cross-spec smoke tests (016 metrics, 017 freshness, 018 deferred-loading) specified at sufficient detail to run post-deployment? [Completeness, Quickstart §8]
- [ ] CHK022 Is the operator-facing rationale for cross-spec verification specified — why these tests, what they catch? [Clarity, Quickstart §8]
- [ ] CHK023 Are the requirements for cross-spec verification cadence specified (only at deploy time? per-release? continuous)? [Gap]

## Future Adapter Onboarding

- [ ] CHK024 Are the operator-facing steps for adding a future adapter specified (4 mechanical steps in quickstart §4)? [Completeness, Quickstart §4]
- [ ] CHK025 Is the contract for verifying a new adapter's deployment specified (banner check, regression suite under the new adapter, FR-005 architectural test)? [Clarity, Quickstart §4]
- [ ] CHK026 Are the requirements for documenting a new adapter's behavior specified (where the new spec lives, how it cross-references this spec)? [Gap]

## Logging and Observability

- [ ] CHK027 Are the requirements for adapter-related log lines specified (level, format, destination, retention)? [Gap]
- [ ] CHK028 Is the contract for `routing_log` schema additions specified (the spec claims no schema changes, but the quickstart references new columns — what's the actual contract)? [Conflict, Plan §"Storage" / Quickstart §5]
- [ ] CHK029 Are the requirements for capturing per-dispatch adapter timings specified (which existing log fields, which new fields, what `@with_stage_timing` decoration covers)? [Completeness, Plan §"Performance Goals" + V14 instrumentation]
- [ ] CHK030 Is the contract for log scrubbing specified for adapter outputs (`provider_message` field in `CanonicalError`, `original_exception` traceback in routing_log)? [Gap]

## Incident Response

- [ ] CHK031 Are the requirements for "LiteLLM outage" incident response specified (does the breaker handle it; does the operator have any role)? [Coverage, Spec §"Edge Cases"]
- [ ] CHK032 Is the contract for "fixture-file corrupted mid-deployment" incident response specified (operator detects via what; recovery is what)? [Gap]
- [ ] CHK033 Are the requirements for "adapter dispatched to wrong adapter due to env-var typo" incident response specified (validator catches at startup; what if it slips through; rollback procedure)? [Completeness, Spec §FR-013 + Quickstart §6]
- [ ] CHK034 Is the contract for "supply-chain compromise of LiteLLM" incident response specified — does the spec name a path to swap to a future direct-Anthropic adapter (per the spec's stated motivation)? [Gap, Spec §"Overview"]

## Container and Deployment Hygiene

- [ ] CHK035 Are the requirements for fixture-file mounting in production containers specified (read-only? per-container? shared volume)? [Gap]
- [ ] CHK036 Is the contract for adapter-package import order at startup specified (deterministic order, single-init guard)? [Completeness, Research §4 + §5]
- [ ] CHK037 Are the requirements for container restart on env-var change specified (env-var changes require restart; no live-reload)? [Completeness, Spec §FR-002 + §FR-015]

## Documentation Completeness

- [ ] CHK038 Is the runbook for adapter operations integrated with existing operational docs (where does this content live; how is it discovered)? [Gap]
- [ ] CHK039 Are the requirements for diagnostic-query maintenance specified (when `routing_log` columns evolve, who updates the queries)? [Gap]
- [ ] CHK040 Is the contract for operator-facing changelog of adapter behaviors specified (what notifies operators of a new mapping in the canonical-error table)? [Gap]
