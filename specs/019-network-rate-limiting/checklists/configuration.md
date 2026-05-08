# Configuration Quality Checklist: Network-Layer Per-IP Rate Limiting

**Purpose**: Validate that spec 019's V16 configuration requirements (the five `SACP_NETWORK_RATELIMIT_*` env vars, validators, default values, type/range specifications, fail-closed semantics, schema-validation boundary, operator workflow, CI-gate alignment, and `docs/env-vars.md` six-field format) are specified at the rigor V16 mandates. This checklist tests configuration-requirement quality, not validator implementation.
**Created**: 2026-05-08
**Feature**: [spec.md §FR-013](../spec.md) + [contracts/env-vars.md](../contracts/env-vars.md) + Constitution §V16

## Env Var Catalog Completeness

- [ ] CHK001 Are all five `SACP_NETWORK_RATELIMIT_*` env vars (`_ENABLED`, `_RPM`, `_BURST`, `_TRUST_FORWARDED_HEADERS`, `_MAX_KEYS`) documented in [contracts/env-vars.md](../contracts/env-vars.md)? [Completeness, Spec §FR-013]
- [ ] CHK002 Does each env var carry all six standard fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec)? [Completeness, Contracts §env-vars]
- [ ] CHK003 Is the deliverable gate "validators + `docs/env-vars.md` sections land BEFORE `/speckit.tasks`" specified as binding, with a CI mechanism named (`scripts/check_env_vars.py` per spec 012 FR-005)? [Verifiability, Spec §FR-013 + Contracts §env-vars "docs/env-vars.md sections"]
- [ ] CHK004 Are the requirements for the `VALIDATORS` tuple in `src/config/validators.py` specified (each of the five validators registered, no missing entries)? [Completeness, Contracts §env-vars "Validator implementation pattern"]
- [ ] CHK005 Is the spec consistent on the count "five env vars" across spec.md, plan.md, contracts/env-vars.md, and quickstart.md (the spec body's `## Configuration (V16)` section labels four explicitly + MAX_KEYS as a fifth umbrella entry — is the umbrella framing reconciled with FR-013's "four" count)? [Consistency, Spec §"Configuration (V16)" + FR-013 + Contracts §env-vars]

## Default Value Specification

- [ ] CHK006 Is the default for `SACP_NETWORK_RATELIMIT_ENABLED` (`false`) specified consistently across spec, contracts, and validator pattern? [Consistency, Contracts §env-vars + Spec §"Configuration (V16)"]
- [ ] CHK007 Is the default for `SACP_NETWORK_RATELIMIT_RPM` (`60`) specified with rationale (one request per second on average per IP, generous for human-driven MCP clients)? [Traceability, Contracts §env-vars + Plan §"Notes for /speckit.tasks"]
- [ ] CHK008 Is the default for `SACP_NETWORK_RATELIMIT_BURST` (`15` = `RPM/4`) specified with the rationale (allows ~15-second bursts at the steady-state rate)? [Traceability, Contracts §env-vars]
- [ ] CHK009 Is the default for `SACP_NETWORK_RATELIMIT_MAX_KEYS` (`100000`) specified with rationale (worst-case ~30MB; raise toward 1M for high-IP-diversity deployments)? [Traceability, Contracts §env-vars + Research §3]
- [ ] CHK010 Is the default for `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS` (`false`) specified with rationale (trust-by-opt-in; immediate peer IP only)? [Traceability, Contracts §env-vars + Spec §"Clarifications"]

## Type and Range Specification

- [ ] CHK011 Is the type for boolean vars (`_ENABLED`, `_TRUST_FORWARDED_HEADERS`) specified precisely enough (string `"true"`/`"false"`, case-insensitive after case-folding)? [Clarity, Contracts §env-vars]
- [ ] CHK012 Is the type for `_RPM` specified precisely (positive integer, requests per minute) with the valid range `[1, 6000]` enumerated? [Clarity, Contracts §env-vars]
- [ ] CHK013 Is the type for `_BURST` specified precisely (positive integer, tokens) with the valid range `[1, 10000]` enumerated? [Clarity, Contracts §env-vars]
- [ ] CHK014 Is the type for `_MAX_KEYS` specified precisely (positive integer; range `[1024, 1000000]`) with the lower bound rationale documented? [Clarity, Contracts §env-vars + Research §3]
- [ ] CHK015 Are the requirements for unparseable-value handling (e.g., `_RPM='abc'`) specified at sufficient detail per validator (`ValidationFailure` with offending var name)? [Completeness, Contracts §env-vars "Validator implementation pattern"]

## Cross-Validator Dependencies

- [ ] CHK016 Is the rule "no cross-validator dependencies among the five vars — each is independently validated" specified explicitly enough to reject scope creep into spec 014's pattern? [Clarity, Contracts §env-vars "Test obligations"]
- [ ] CHK017 Is the contract "when `_ENABLED=true` and `_RPM` is unset, the validator uses the default 60 (no startup exit)" specified clearly enough to apply consistently? [Clarity, Contracts §env-vars `_RPM` "Note"]
- [ ] CHK018 Are the requirements for the divergence from spec 014's cross-validator precedent (this spec deliberately has no equivalent coupling) documented to prevent reviewers from expecting one? [Clarity, Contracts §env-vars "Test obligations"]

## Fail-Closed Semantics (V15 + V16)

- [ ] CHK019 Are the requirements for "validators run BEFORE binding any port or accepting any connection" specified as binding for all five new validators? [Completeness, Constitution §V16 + Plan §"Constitution Check V16"]
- [ ] CHK020 Is the contract "invalid env-var values exit at startup with a clear error message naming the offending var" specified at the same fidelity for all five vars? [Consistency, Spec §SC-007 + Contracts §env-vars]
- [ ] CHK021 Are the requirements for the FR-014 byte-identical-when-unset contract specified — when all five vars are unset, no middleware registered, no rejections, no audit entries? [Completeness, Spec §FR-014 + SC-006]
- [ ] CHK022 Is the contract for "unparseable boolean values cause startup exit" specified for both boolean vars (`_ENABLED`, `_TRUST_FORWARDED_HEADERS`)? [Clarity, Spec §"Configuration (V16)" + Contracts §env-vars]
- [ ] CHK023 Is the exit-code-on-validator-failure contract specified, or is it implicit (likely non-zero, but unspecified)? [Gap]

## Schema-Validation Boundary

- [ ] CHK024 Is the boundary between "validator-time check" (range, type, parseability) and "runtime check" (e.g., source-IP-unresolvable per FR-012) specified clearly enough to avoid duplicating logic? [Clarity, Contracts §env-vars + Spec §FR-012]
- [ ] CHK025 Are the requirements for validator output shape (`ValidationFailure | None`) specified consistently with the existing `src/config/validators.py` pattern? [Consistency, Contracts §env-vars "Validator implementation pattern"]
- [ ] CHK026 Is the contract "the validator's failure message names the offending var explicitly" specified at sufficient detail (operator reads error, knows which var to fix)? [Clarity, Spec §SC-007 + Contracts §env-vars]

## Operator Workflow

- [ ] CHK027 Are the operator paths for "enable the limiter" specified at sufficient detail (set `_ENABLED=true`, set RPM/BURST/MAX_KEYS, restart, verify config validation log line)? [Completeness, Quickstart §"Enable the limiter"]
- [ ] CHK028 Are the operator paths for "rollback to pre-feature behavior with all five vars unset" specified at sufficient detail (unset OR set `_ENABLED=false`; restart; no audit entries from that point)? [Completeness, Quickstart §"Disable the limiter"]
- [ ] CHK029 Are the operator paths for "tune the limit under flood" specified at sufficient detail (raise `_RPM`, raise `_BURST` proportionally, restart)? [Completeness, Quickstart §"Tune the limit"]
- [ ] CHK030 Is the operator path for "enable forwarded-header trust" specified with the prerequisite warning (proxy must sanitize upstream headers)? [Clarity, Quickstart §"Tune the limit" + Contracts §env-vars `_TRUST_FORWARDED_HEADERS` "Note"]
- [ ] CHK031 Is the operator-visible config-validation log line specified (`"Config validation: 5 SACP_NETWORK_RATELIMIT_* validators passed"`) at sufficient detail to grep for in deployment? [Clarity, Quickstart §"Enable the limiter"]

## CI Gate Alignment

- [ ] CHK032 Is the alignment with `scripts/check_env_vars.py` specified — the CI gate flags any var with a validator but no docs section, and vice versa? [Completeness, Contracts §env-vars "docs/env-vars.md sections"]
- [ ] CHK033 Are the requirements for V16 deliverable-gate timing specified (validators + `docs/env-vars.md` sections land BEFORE `/speckit.tasks` is run)? [Verifiability, Spec §FR-013 + Plan §"Constitution Check V16"]
- [ ] CHK034 Is the contract for "validator must be appended to `VALIDATORS` tuple" enforced by something other than reviewer attention (e.g., a CI gate checking tuple membership against the docs sections)? [Gap]

## Topology-7 Forward-Compatibility

- [ ] CHK035 Is the contract for env-var behavior in topology 7 specified — when `SACP_TOPOLOGY=7` and the orchestrator has no inbound HTTP surface, do the five vars matter at all? [Completeness, Research §8 + Spec §V12]
- [ ] CHK036 Are the requirements documented for "middleware is registered but idle in topology 7" — env vars are still validated at startup; the middleware just sees no traffic? [Clarity, Research §8]

## Docs Section Quality

- [ ] CHK037 Are the env-var docs sections written with operator-facing language (not implementer-facing — e.g., "raise `_RPM` for NAT-fronted traffic" rather than "the validator clamps to range")? [Clarity, Contracts §env-vars + Quickstart §"Tune the limit"]
- [ ] CHK038 Is the cross-reference between contracts/env-vars.md and `docs/env-vars.md` specified — are they intended to mirror, or does contracts/ act as a draft for `docs/`? [Gap]
- [ ] CHK039 Are the docs sections specified with the same six-field shape as existing `docs/env-vars.md` entries (consistency with the established convention)? [Consistency, Contracts §env-vars "docs/env-vars.md sections"]

## V16 Catalog Completeness

- [ ] CHK040 Does the spec acknowledge that the middleware-registration env-var read happens AFTER `validate_all()` but uses the same env-var values, with no race / TOCTOU concern? [Gap]

## Notes

Highest-impact open items:
- CHK005 calls out a [Consistency] concern: the spec body labels four env vars + MAX_KEYS as an umbrella; FR-013 says "four"; contracts/env-vars.md and the validator pattern enumerate five. Recommend reconciling the count language before tasks.
- CHK023 ([Gap]) on exit-code on validator failure — leaving this implicit makes operator runbooks harder to write.
- CHK034 ([Gap]) on CI-gate enforcement of `VALIDATORS` tuple membership — currently relies on reviewer attention; a structural test would catch silent omissions.
- CHK038 ([Gap]) on the contracts/env-vars.md ↔ docs/env-vars.md mirror semantics — clarifying which is the source of truth would prevent drift.

Use the `[PASS] / [PARTIAL] / [GAP] / [DRIFT] / [ACCEPTED]` annotation convention when triaging items.
