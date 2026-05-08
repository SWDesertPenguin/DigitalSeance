# Operations Quality Checklist: AI Response Shaping (Verbosity Reduction + Register Slider)

**Purpose**: Validate that spec 021's operational requirements (deployment, runbook, recovery, monitoring, rollback, calibration) are specified clearly enough for operators and facilitators to apply during deployment and incident response. This checklist tests operations-requirement quality, not the operational tooling.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [quickstart.md](../quickstart.md)

## Deployment Workflow

- [ ] CHK001 Are the requirements for first-deployment of the response-shaping feature specified at sufficient detail (V16 gate landed BEFORE `/speckit.tasks` per FR-014; operator sets master switch to opt in; `SACP_RESPONSE_SHAPING_ENABLED` defaults `false` for v1)? [Completeness, Quickstart §1 + Spec §FR-014]
- [ ] CHK002 Is the contract for `python -m src.run_apps --validate-config-only` specified at sufficient detail (operator can verify config before restart)? [Clarity, Quickstart §1]
- [ ] CHK003 Are the requirements for verifying the deployment specified (drive a hedge-heavy turn, query `routing_log` for shaping rows, observe `shaping_reason` column values)? [Completeness, Quickstart §1]
- [ ] CHK004 Is the rollout sequence specified — can spec 021 land in a single deployment, or does it require a phased rollout (e.g., V16 gate first, then code, then enable)? [Clarity, Tasks §"Phase 2" + Plan §"Notes for /speckit.tasks"]

## Runbook for Facilitator Slider/Override Workflows

- [ ] CHK005 Are the operator paths for "set the session-level register slider" specified at sufficient detail (facilitator API direct until spec 011 ships; `/me` reflects on next query; audit log records the change)? [Completeness, Quickstart §3]
- [ ] CHK006 Are the operator paths for "set a per-participant override" specified at sufficient detail (facilitator-only mutation, `/me` returns `register_source='participant_override'` for the targeted participant only, other participants unaffected)? [Completeness, Quickstart §4]
- [ ] CHK007 Are the operator paths for "clear an explicit override" specified at sufficient detail (facilitator clears → participant falls back to session register; explicit clear emits `participant_register_override_cleared`; cascade does NOT)? [Clarity, Quickstart §4 + Contracts §"audit-events.md"]
- [ ] CHK008 Is the rule "operator authority boundary — env vars are deployment surfaces; slider + override are facilitator runtime surfaces" specified clearly enough to prevent confusion at runbook time? [Clarity, Quickstart §"Operator authority boundary"]

## Failure Diagnostic Queries

- [ ] CHK009 Is the diagnostic query for the three new `admin_audit_log` event types specified clearly enough to run against any orchestrator deployment? [Clarity, Quickstart §3-4 + Contracts §"audit-events.md"]
- [ ] CHK010 Are the requirements for the `routing_log` shaping columns (`shaping_score_ms`, `shaping_retry_dispatch_ms`, `filler_score`, `shaping_retry_delta_text`, `shaping_reason`) specified at sufficient detail for diagnostic queries? [Completeness, Data-model §"routing_log extension" + Quickstart §1]
- [ ] CHK011 Is the operator path for "list overrides in this session" specified at sufficient detail (uses `participant_register_override_session_idx` for performance)? [Clarity, Research §7]
- [ ] CHK012 Is the `shaping_reason` enum specified clearly enough for diagnostic queries to filter (`null`, `'filler_retry'`, `'filler_retry_exhausted'`, `'shaping_pipeline_error'`)? [Completeness, Data-model §"routing_log extension"]

## Misconfiguration Recovery

- [ ] CHK013 Are the recovery paths for each documented startup failure mode specified (three SACP_* validators × distinct error messages each)? [Completeness, Quickstart §"Troubleshooting"]
- [ ] CHK014 Is the recovery path for `shaping_reason='filler_retry_exhausted'` on every turn specified clearly enough for an operator to identify the root cause (threshold too tight; or model genuinely insensitive to delta)? [Clarity, Quickstart §"Troubleshooting"]
- [ ] CHK015 Is the recovery path for `shaping_reason='shaping_pipeline_error'` specified at sufficient detail to identify the root cause (sentence-transformers gone, regex bug, embedding decode failure)? [Completeness, Quickstart §"Troubleshooting"]
- [ ] CHK016 Are the requirements for "session continues on every fail-closed path; one bad draft does not gate the loop" specified at sufficient detail to set operator expectations? [Clarity, Spec §"Edge Cases" + Contracts §"Fail-closed contract"]

## V14 Performance Monitoring

- [ ] CHK017 Are the V14 budget verification queries specified at sufficient detail (P95 query for `shaping_score_ms` in last hour; comparison to the 50ms budget)? [Completeness, Quickstart §5]
- [ ] CHK018 Is the contract "delta MUST fit within V14 per-stage budget tolerance" specified with a numeric threshold per budget (50ms for scorer; <1ms for slider lookup; tracking existing per-turn dispatch P95 for retry dispatch)? [Measurability, Spec §"Performance Budgets"]
- [ ] CHK019 Are the requirements for "regressing scorer detection" specified — a future `_HEDGE_TOKENS` list expansion that explodes regex cost shows up as `shaping_score_ms` regression? [Clarity, Quickstart §5]
- [ ] CHK020 Is the operator path for "V14 budget violation detected" specified — what runbook do they follow, who do they escalate to? [Gap]

## Incident Response

- [ ] CHK021 Are the requirements for "high retry rate" incident response specified (threshold-tightening loop in quickstart §2 — retry rate > 0.30 likely too low; rate < 0.05 likely too high)? [Completeness, Quickstart §2]
- [ ] CHK022 Is the SC-002 master-switch turnoff procedure specified at sufficient detail (set `SACP_RESPONSE_SHAPING_ENABLED=false`, restart, verify byte-identical pre-feature behavior)? [Completeness, Quickstart §6 + Spec §SC-002]
- [ ] CHK023 Are the requirements for "model genuinely insensitive to tightened delta" incident response specified (per-family score-distribution query in quickstart §2; investigate model-specific tendencies)? [Clarity, Quickstart §2 + Spec §"Edge Cases"]
- [ ] CHK024 Are the requirements for "override survives participant remove" incident response specified (cascade not firing; investigate FK constraint on `participant_register_override.participant_id`)? [Clarity, Quickstart §"Troubleshooting"]
- [ ] CHK025 Is the contract for "shaping retry dispatch dominates per-turn cost" incident response specified (raise threshold OR investigate provider-side latency; per FR-006 each retry consumes one compound-retry slot)? [Completeness, Quickstart §"Troubleshooting"]

## Per-Family Threshold Calibration Loop

- [ ] CHK026 Is the calibration-loop documentation specified clearly enough to apply (operator observes the score-distribution query per family, then tunes either the env var uniformly or files an amendment for per-family changes)? [Completeness, Quickstart §2 + Research §9]
- [ ] CHK027 Are the requirements for "when to revisit defaults" specified — Phase 3 production observation may justify a per-family tightening via a follow-up amendment? [Clarity, Research §9 + Spec §"Assumptions"]
- [ ] CHK028 Is the contract "the placeholder `0.6` from spec §Configuration stays as the env-var-uniform override default; per-family defaults apply when env var unset" specified consistently across spec, contracts, research, and quickstart? [Consistency, Spec §"Configuration (V16)" + Research §9 + Contracts §"SACP_FILLER_THRESHOLD"]

## Phase 3 Readiness Checks

- [ ] CHK029 Is the Phase 3 declaration prerequisite (recorded 2026-05-05) specified at sufficient detail — no additional dependency on spec 013 / 014 implementation status? [Clarity, Plan §"Notes for /speckit.tasks"]
- [ ] CHK030 Are the requirements for V16 deliverable gate landing BEFORE `/speckit.tasks` runs specified clearly enough to apply at task-creation time? [Verifiability, Spec §FR-014]

## Logging and Observability

- [ ] CHK031 Are the requirements for shaping-related log lines specified (level, format, destination, retention)? [Gap]
- [ ] CHK032 Is the contract for `routing_log` schema additions specified consistently between plan §"Storage" (claims new per-stage timing columns + three decision columns), data-model (lists five columns), and the contract documents? [Consistency, Plan §"Storage" + Data-model §"routing_log extension"]
- [ ] CHK033 Are the requirements for log scrubbing specified for shaping outputs (`shaping_retry_delta_text` is operator-controlled fixed text, but the scorer's pre-retry score and post-retry score are content-derived signals — does any leakage risk arise)? [Gap]

## Container and Deployment Hygiene

- [ ] CHK034 Is the contract for module-import order at startup specified (V16 validators run before adapter init; the topology-7 gate runs at shaping-pipeline init, not validator-time)? [Completeness, Research §10]
- [ ] CHK035 Are the requirements for container restart on env-var change specified (env-var changes require restart; no live-reload — facilitator runtime tools like the slider DO support mid-session changes)? [Completeness, Quickstart §"Operator authority boundary"]

## Documentation Completeness

- [ ] CHK036 Is the runbook for shaping operations integrated with existing operational docs (where does this content live; how is it discovered)? [Gap]
- [ ] CHK037 Are the requirements for diagnostic-query maintenance specified (when `routing_log` columns evolve, who updates the queries)? [Gap]
- [ ] CHK038 Is the contract for operator-facing changelog of shaping behaviors specified (what notifies operators of a per-family threshold change)? [Gap]

## Notes

Highest-impact open items at draft time: CHK020 (V14 budget-violation escalation path is unspecified — common gap across V14 specs), CHK031 + CHK033 (shaping-related log line specifications and scrubbing rules are implicit; the `shaping_retry_delta_text` is fixed operator-controlled text but the score signals are content-derived), CHK036-CHK038 (runbook integration, query maintenance cadence, and operator-facing changelog patterns are all unaddressed). Annotation convention for runs of this checklist: `[PASS]`, `[PARTIAL]`, `[GAP]`, `[DRIFT]`, `[ACCEPTED]`. `[PARTIAL]` is the right marker for items where the spec/quickstart names a workflow but stops short of an end-to-end operational runbook.
