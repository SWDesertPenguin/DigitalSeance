# Security Requirements Quality Checklist: Network-Layer Per-IP Rate Limiting

**Purpose**: Validate that the spec's security requirements are complete, unambiguous, consistent, and measurable. This is a unit-test-for-English: it tests the writing of the requirements, not the eventual implementation.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md)

## Threat Model Coverage

- [ ] CHK001 Is the bcrypt-DoS threat model documented with attacker-capability assumptions explicit (token grammar known, no valid token required)? [Completeness, Spec §Overview]
- [ ] CHK002 Are pre-auth and post-auth attack surfaces clearly partitioned in the spec, with explicit ownership per layer (network-layer = pre-auth; §7.5 = post-auth)? [Clarity, Spec §FR-007/FR-008]
- [ ] CHK003 Are the NAT / corporate-proxy / VPN-exit shared-IP scenarios named as known false-positive sources, and is operator mitigation guidance specified? [Coverage, Spec §Edge Cases]
- [ ] CHK004 Is the spoofed-`X-Forwarded-For` threat addressed with explicit operator-responsibility language for proxy header sanitization? [Completeness, Spec §FR-011]
- [ ] CHK005 Are malformed-connection / source-IP-unresolvable cases specified with deterministic rejection (HTTP 400) rather than fail-open default? [Clarity, Spec §FR-012]

## Layer Non-Interaction Guarantee

- [ ] CHK006 Is the "MUST NOT share state" requirement quantified with specific forbidden interactions (read, write, mutual call)? [Clarity, Spec §FR-007]
- [ ] CHK007 Are the four non-interaction acceptance scenarios (US2 AS1-AS4) sufficient to cover state, timing, and budget independence between the two limiters? [Coverage, Spec §US2]
- [ ] CHK008 Is the SC-004 §7.5 byte-identical-behavior contract measurable via a CI-runnable test (not a subjective review)? [Measurability, Spec §SC-004]
- [ ] CHK009 Does the spec specify which of cost-tracking, participant-rate-counter, conversation-state, and audit-log-categories MUST remain unchanged on a network-layer rejection? [Completeness, Spec §SC-005]

## Recon Safety (Audit + Metrics Privacy)

- [ ] CHK010 Are the forbidden label/field contents enumerated for `sacp_rate_limit_rejection_total` (no source IP, no query string, no headers, no body)? [Clarity, Spec §FR-010]
- [ ] CHK011 Is `source_ip_keyed` defined with an explicit canonical CIDR-string form, distinguishing it from raw IPv6 host addresses? [Clarity, Spec §FR-004 / Spec §US3 AS1]
- [ ] CHK012 Does SC-009 specify the privacy-contract test scope (raw-IPv6 absence, no query string, no headers, no body) precisely enough to be a CI gate? [Measurability, Spec §SC-009]
- [ ] CHK013 Is the metric cardinality bound specified (label-set values + count) so that high-cardinality recon attacks are prevented at the metric layer? [Gap]

## Fail-Closed and Master-Switch Semantics

- [ ] CHK014 Is the unset-env-var baseline ("byte-identical to pre-feature behavior") specified for every observable surface (middleware presence, audit entries, metric existence)? [Completeness, Spec §FR-014]
- [ ] CHK015 Are the V16 fail-closed-on-invalid-value semantics specified for all five env vars, with the distinction between "unset" and "invalid" made explicit? [Clarity, Spec §Configuration / SC-007]
- [ ] CHK016 Does the spec define what "valid" means per env var precisely enough that a validator function can be written from the spec text alone? [Measurability, Spec §FR-013 / Configuration §each var]

## IPv6 Keying Privacy

- [ ] CHK017 Is the /64 keying decision documented with the privacy-vs-effectiveness tradeoff (RFC 4941 privacy-extension rotation defeating /128 keying)? [Clarity, Spec §C5 resolution / FR-004]
- [ ] CHK018 Is the per-/64 collateral-damage risk for legitimate clients sharing a /64 acknowledged with operator mitigation guidance? [Coverage, Spec §Edge Cases]

## Audit-Log Forensic Value vs Volume Tradeoff

- [ ] CHK019 Is the per-(IP, minute) coalescing window quantified with a single-minute granularity, and is the metric counter's per-rejection precision called out as the offset for forensic loss? [Clarity, Spec §FR-009 / §Assumptions]
- [ ] CHK020 Does SC-008 specify the upper-bound entry count formula in terms of unique flooding IPs and minutes, making the bound testable? [Measurability, Spec §SC-008]
- [ ] CHK021 Is the audit-only field set (source_ip_keyed, endpoint_path, method, rejected_at, limiter_window_remaining_s, rejection_count) sufficient to identify a flooding incident without consulting application logs? [Completeness, Spec §US3 AS4]

## Edge-Case Coverage

- [ ] CHK022 Are non-GET methods on exempt paths (e.g., `POST /metrics`) specified to fall through to normal limiting? [Coverage, Spec §Edge Cases / FR-006]
- [ ] CHK023 Is post-auth failure (token-expired, participant-suspended) specified to leave the limiter increment in place? [Coverage, Spec §Edge Cases]
- [ ] CHK024 Is the WebSocket upgrade single-request-at-upgrade-time semantics specified, with subsequent in-band traffic explicitly out of network-layer scope? [Clarity, Spec §FR-015 / Edge Cases]

## Notes

- Items marked [Gap] require spec amendment.
- Items marked [Ambiguity] require a Clarifications-block resolution before /speckit.tasks runs.
- Pass/fail markers ([PASS] / [PARTIAL] / [GAP] / [DRIFT] / [ACCEPTED]) replace emoji status; mark inline as the checklist is reviewed.
