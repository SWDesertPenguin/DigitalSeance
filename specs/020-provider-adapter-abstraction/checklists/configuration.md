# Configuration Quality Checklist: Pluggable Provider Adapter Abstraction

**Purpose**: Validate that spec 020's V16 configuration requirements (env vars, validators, docs sections, fail-closed semantics) are specified at the rigor V16 mandates. This checklist tests configuration-requirement quality, not validator implementation.
**Created**: 2026-05-08
**Feature**: [spec.md §FR-013](../spec.md) + [contracts/env-vars.md](../contracts/env-vars.md) + Constitution §V16

## Env Var Catalog Completeness

- [ ] CHK001 Are both new env vars (`SACP_PROVIDER_ADAPTER`, `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`) documented in [contracts/env-vars.md](../contracts/env-vars.md)? [Completeness, Spec §FR-013]
- [ ] CHK002 Does each env var carry all six standard fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec)? [Completeness, Contracts §env-vars]
- [ ] CHK003 Is the deliverable gate "validators + docs/env-vars.md sections land BEFORE `/speckit.tasks`" specified as binding, with a CI mechanism named (`scripts/check_env_vars.py`)? [Verifiability, Spec §FR-013]
- [ ] CHK004 Are the requirements for the `VALIDATORS` tuple in `src/config/validators.py` specified (registration order, append-vs-replace semantics)? [Completeness, Tasks §T007 + Contracts §env-vars]

## Default Value Specification

- [ ] CHK005 Is the default for `SACP_PROVIDER_ADAPTER` (unset → `litellm`) specified consistently across spec, contracts, and validator? [Consistency]
- [ ] CHK006 Is the default behavior for `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` (unset is allowed when adapter is non-mock; required when adapter is mock) specified at sufficient detail to mechanically apply? [Clarity, Contracts §env-vars]
- [ ] CHK007 Is the rationale for choosing `litellm` as the default (preserving FR-014 byte-identical regression contract) documented? [Traceability, Contracts §env-vars]

## Type and Range Specification

- [ ] CHK008 Is the type for `SACP_PROVIDER_ADAPTER` specified precisely enough (string + case-folding rule + lookup table)? [Clarity, Contracts §env-vars]
- [ ] CHK009 Are the valid values for `SACP_PROVIDER_ADAPTER` enumerated explicitly (v1: `litellm`, `mock`; future adapters extend in their landing PRs)? [Completeness, Research §9 + Contracts §env-vars]
- [ ] CHK010 Is the type for `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` specified precisely (filesystem path; readability check; JSON-parseable check)? [Clarity, Contracts §env-vars]
- [ ] CHK011 Are the requirements for symbolic-link handling, relative-vs-absolute path semantics, and tilde-expansion specified for the fixtures-path var? [Gap, Contracts §env-vars]

## Cross-Validator Dependencies

- [ ] CHK012 Is the cross-validator dependency between the two env vars specified (mock adapter requires fixtures-path; non-mock ignores it)? [Completeness, Research §9 + Contracts §env-vars]
- [ ] CHK013 Is the validator implementation pattern specified clearly enough to mirror spec 014's precedent (`SACP_AUTO_MODE_ENABLED` ↔ `SACP_DMA_DWELL_TIME_S`)? [Traceability, Research §9]
- [ ] CHK014 Are the failure-message strings for the cross-validator specified at sufficient detail (operator reads the error, knows what to fix)? [Clarity, Contracts §env-vars]
- [ ] CHK015 Is the order in which the two validators run within the `VALIDATORS` tuple specified, and the rationale documented? [Completeness, Tasks §T007 + Contracts §env-vars]

## Fail-Closed Semantics (V15 + V16)

- [ ] CHK016 Are the three failure modes for `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` (unset+mock, not-readable, invalid-JSON) each specified with a distinct error message? [Completeness, Contracts §env-vars]
- [ ] CHK017 Is the requirement "validators run BEFORE binding any port or accepting any connection" stated as binding for these two new validators? [Completeness, Constitution §V16]
- [ ] CHK018 Are the requirements for "validator failure causes process to exit with clear error" specified at the same fidelity for both new vars? [Consistency, Spec §FR-013]
- [ ] CHK019 Is the contract for "exit code on validator failure" specified, or is it implicit (likely non-zero, but unspecified)? [Gap]

## Schema Validation Boundary

- [ ] CHK020 Is the boundary between "validator-time check" (file readability, JSON parse) and "adapter-init-time check" (deeper schema validation, capability set existence) specified? [Clarity, Contracts §env-vars]
- [ ] CHK021 Are the requirements for `MockFixtureSchemaError` raise behavior at adapter-init time specified to fail-close before port binding? [Completeness, Contracts §env-vars]
- [ ] CHK022 Is the contract for "schema validation rejects unknown top-level keys" specified, or are unknown keys silently ignored? [Gap, Contracts §mock-fixtures]

## Operator Workflow

- [ ] CHK023 Are the operator paths for "switch to mock adapter" specified at sufficient detail (set both env vars, restart, verify banner)? [Completeness, Quickstart §3]
- [ ] CHK024 Are the operator paths for "rollback to LiteLLM adapter" specified (unset env vars OR set adapter back to litellm; restart)? [Completeness, Quickstart §3]
- [ ] CHK025 Are the diagnostic queries for "verify which adapter is active" specified at runtime (banner check, `routing_log.adapter_name` query)? [Completeness, Quickstart §5]
- [ ] CHK026 Is the requirement for the startup banner to include adapter name + selection reason specified clearly enough to implement consistently? [Clarity, Tasks §T043 + Quickstart §1]

## CI Gate Alignment

- [ ] CHK027 Is the alignment with `scripts/check_env_vars.py` specified — does the CI gate scan for `os.environ.get("SACP_PROVIDER_ADAPTER*")` and verify each has a docs section? [Completeness, Contracts §env-vars]
- [ ] CHK028 Are the requirements for V16 deliverable-gate timing specified (validators + docs land before `/speckit.tasks` is run)? [Verifiability, Spec §FR-013]
- [ ] CHK029 Is the contract for "validator must be appended to `VALIDATORS` tuple" enforced by something other than reviewer attention (e.g., a CI gate checking tuple membership)? [Gap]

## Topology-7 Forward-Compatibility

- [ ] CHK030 Is the contract for env-var behavior in topology 7 specified — when `SACP_TOPOLOGY=7`, do the two new vars matter at all? [Gap, Research §10]
- [ ] CHK031 Are the requirements for the topology-7 gate's env-var read documented (read at adapter-init time only, not per-dispatch)? [Clarity, Research §10]

## Future-Adapter Extension

- [ ] CHK032 Is the procedure for extending `SACP_PROVIDER_ADAPTER`'s valid range when a new adapter spec lands specified (validator amendment, docs section addition)? [Completeness, Quickstart §4]
- [ ] CHK033 Are the requirements for "the validator hardcodes the v1 set; future adapters extend in their landing PRs" specified clearly enough to apply consistently? [Clarity, Research §9]

## Docs Section Quality

- [ ] CHK034 Are the env-var docs sections written with operator-facing language (not implementer-facing)? [Clarity, Contracts §env-vars]
- [ ] CHK035 Is the cross-reference between contracts/env-vars.md and `docs/env-vars.md` specified — are they intended to mirror, or does contracts/ act as a draft for `docs/`? [Gap]
- [ ] CHK036 Are the docs sections specified with the same six-field shape as existing `docs/env-vars.md` entries (consistency with established convention)? [Consistency, Contracts §env-vars]

## V16 Catalog Completeness Gap

- [ ] CHK037 Does the spec acknowledge that the adapter-init env-var read happens AFTER `validate_all()` but uses the same env-var values, with no race / TOCTOU concern? [Gap, Plan §"Technical Context"]
