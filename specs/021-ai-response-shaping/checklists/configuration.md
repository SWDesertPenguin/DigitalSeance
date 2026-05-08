# Configuration Quality Checklist: AI Response Shaping (Verbosity Reduction + Register Slider)

**Purpose**: Validate that spec 021's V16 configuration requirements (three new env vars, validators, docs sections, fail-closed semantics, and the per-family threshold defaults baked into `BehavioralProfile`) are specified at the rigor V16 mandates. This checklist tests configuration-requirement quality, not validator implementation.
**Created**: 2026-05-08
**Feature**: [spec.md §FR-014](../spec.md) + [contracts/env-vars.md](../contracts/env-vars.md) + Constitution §V16

## Env Var Catalog Completeness

- [ ] CHK001 Are all three new env vars (`SACP_FILLER_THRESHOLD`, `SACP_REGISTER_DEFAULT`, `SACP_RESPONSE_SHAPING_ENABLED`) documented in [contracts/env-vars.md](../contracts/env-vars.md)? [Completeness, Spec §FR-014]
- [ ] CHK002 Does each env var carry all six standard fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec)? [Completeness, Contracts §env-vars]
- [ ] CHK003 Is the deliverable gate "validators + `docs/env-vars.md` sections land BEFORE `/speckit.tasks`" specified as binding, with the CI mechanism named (`scripts/check_env_vars.py`)? [Verifiability, Spec §FR-014 + Contracts §"CI-gate alignment"]
- [ ] CHK004 Are the requirements for the `VALIDATORS` tuple in `src/config/validators.py` specified (three new validators appended; registration order; append-only semantics)? [Completeness, Tasks §T006 + Contracts §"CI-gate alignment"]

## Default Value Specification

- [ ] CHK005 Is the default for `SACP_FILLER_THRESHOLD` (unset → per-family default from `BehavioralProfile` dict) specified consistently across spec, contracts, research, and quickstart? [Consistency, Contracts §"SACP_FILLER_THRESHOLD" + Research §9]
- [ ] CHK006 Is the default for `SACP_REGISTER_DEFAULT` (`2` Conversational) specified with rationale (matches observed default tone of Phase 1+2 sessions)? [Traceability, Spec §"Configuration (V16)" + Contracts §"SACP_REGISTER_DEFAULT"]
- [ ] CHK007 Is the default for `SACP_RESPONSE_SHAPING_ENABLED` (`false` for v1, opt-in) specified with the future-flip path documented (once SC-001's calibration target is validated, default may flip in a follow-up amendment)? [Completeness, Contracts §"SACP_RESPONSE_SHAPING_ENABLED"]

## Type and Range Specification

- [ ] CHK008 Is the type for `SACP_FILLER_THRESHOLD` specified precisely (float in `[0.0, 1.0]` inclusive, with semantic meaning of bounds documented — near 0.0 flags everything, near 1.0 flags nothing)? [Clarity, Contracts §"SACP_FILLER_THRESHOLD"]
- [ ] CHK009 Is the type for `SACP_REGISTER_DEFAULT` specified precisely (integer in `[1, 5]` inclusive, mapped to the five preset names)? [Clarity, Contracts §"SACP_REGISTER_DEFAULT"]
- [ ] CHK010 Is the type for `SACP_RESPONSE_SHAPING_ENABLED` specified precisely (boolean: `true`/`false` case-insensitive; `1`/`0` accepted per existing validator convention)? [Clarity, Contracts §"SACP_RESPONSE_SHAPING_ENABLED"]
- [ ] CHK011 Are the requirements for "empty / unset" handling specified per validator (each var's allowed-empty rule is enumerated in tasks T011)? [Completeness, Tasks §T011]

## Cross-Validator Dependencies

- [ ] CHK012 Is the rule "no cross-validator dependencies among the three vars — each is independently validated" specified explicitly, contrasting with spec 014's cross-validator pair? [Clarity, Contracts §"CI-gate alignment"]
- [ ] CHK013 Are the requirements for the `BehavioralProfile` dict (which holds per-family thresholds) specified as INDEPENDENT of the env-var validators (the profile dict is loaded later, at adapter init, not at validator-time)? [Gap]

## Per-Family Threshold Defaults (BehavioralProfile dict)

- [ ] CHK014 Is the per-family threshold split (anthropic/openai `0.60`; gemini/groq/ollama/vllm `0.55`) documented as the authoritative source, with rationale tied to Phase 1+2 shakedown observations? [Completeness, Research §9]
- [ ] CHK015 Is the relationship between the env var (when set, overrides every family uniformly) and the per-family default (applies when env var unset) specified at sufficient detail to apply consistently? [Clarity, Research §9 + Contracts §"SACP_FILLER_THRESHOLD"]
- [ ] CHK016 Is the rule "per-family thresholds are NOT env vars but ARE configurable defaults baked into the `BehavioralProfile` dict" specified clearly enough that operators don't expect six per-family env vars to exist? [Clarity, Research §9]
- [ ] CHK017 Are the requirements for the per-family threshold authoritative source documented (single location in `src/orchestrator/shaping.py`; no second copy in docs that could drift)? [Gap, Research §1]
- [ ] CHK018 Is the calibration-loop documentation specified in quickstart (operators observe `routing_log.shaping_score_ms` and the score distribution per family, then tune either the env var or file an amendment for per-family changes)? [Completeness, Quickstart §2 + Research §9]

## Fail-Closed Semantics (V15 + V16)

- [ ] CHK019 Are the failure modes for `SACP_FILLER_THRESHOLD` (non-float, `< 0.0`, `> 1.0`) each specified with a distinct error path? [Completeness, Data-model §"Validation rules"]
- [ ] CHK020 Are the failure modes for `SACP_REGISTER_DEFAULT` (non-integer, `< 1`, `> 5`) each specified with a distinct error path? [Completeness, Data-model §"Validation rules"]
- [ ] CHK021 Are the failure modes for `SACP_RESPONSE_SHAPING_ENABLED` (not in `{true, false}` case-insensitive AND not in `{0, 1}`) each specified with a distinct error path? [Completeness, Data-model §"Validation rules"]
- [ ] CHK022 Is the requirement "validators run BEFORE binding any port or accepting any connection" specified as binding for these three new validators per Constitution §V16? [Completeness, Constitution §V16 + Spec §FR-014]
- [ ] CHK023 Is the contract for "exit code on validator failure" specified, or is it implicit (likely non-zero, but unspecified)? [Gap]
- [ ] CHK024 Are the requirements for "fail-closed error message naming the offending var" specified at the same fidelity for all three vars (consistent error-message convention)? [Consistency, Spec §SC-008 + Quickstart §"Troubleshooting"]

## V16 Deliverable-Gate Completeness

- [ ] CHK025 Is the rule "validators + docs/env-vars.md sections land BEFORE `/speckit.tasks` is run" specified consistently across FR-014, plan §"Constitution Check V16", and tasks Phase 2? [Consistency, Spec §FR-014 + Plan §"V16" + Tasks §"V16 deliverable gate"]
- [ ] CHK026 Are the requirements for V16 deliverable-gate timing specified at sufficient detail to mechanically apply (T003-T010 in tasks ordered before any code-path work)? [Verifiability, Tasks §"Phase 2"]
- [ ] CHK027 Is the contract "validator must be appended to `VALIDATORS` tuple" enforced by something other than reviewer attention (e.g., a CI gate or test)? [Gap, Tasks §T006]
- [ ] CHK028 Are the validator-unit-test requirements specified (T011 covers each validator — valid value passes, out-of-range raises `ConfigValidationError` naming the offending var)? [Completeness, Tasks §T011]

## CI-Gate Alignment

- [ ] CHK029 Is the alignment with `scripts/check_env_vars.py` specified — does the CI gate scan for `os.environ.get("SACP_*")` calls and verify each has a docs section? [Completeness, Contracts §"CI-gate alignment"]
- [ ] CHK030 Are the requirements for the V16 baseline check (T001 confirms baseline passes before new validators land) specified at sufficient detail to apply at branch-creation time? [Completeness, Tasks §T001 + T010]

## Operator Workflow

- [ ] CHK031 Are the operator paths for "enable shaping" specified at sufficient detail (set master switch, optionally tune threshold, restart, observe `routing_log` shaping rows)? [Completeness, Quickstart §1]
- [ ] CHK032 Are the operator paths for "tune the threshold" specified at sufficient detail (raise to fire fewer retries; lower to fire more; per-family tightening requires §14.2 amendment)? [Completeness, Quickstart §2]
- [ ] CHK033 Are the operator paths for "rollback to pre-feature behavior" specified at sufficient detail (unset master switch, restart, verify byte-identical pre-feature acceptance tests pass per SC-002)? [Completeness, Quickstart §6]
- [ ] CHK034 Is the operator authority boundary specified clearly (env vars are deployment surfaces; slider + override are facilitator runtime surfaces)? [Clarity, Quickstart §"Operator authority boundary"]

## Topology-7 Forward-Compatibility

- [ ] CHK035 Is the contract for env-var behavior in topology 7 specified — when `SACP_TOPOLOGY=7`, the three new vars are still validated unconditionally (gate is at consumer, not validator)? [Completeness, Research §10]
- [ ] CHK036 Are the requirements for the topology-7 forward-document pattern specified at sufficient detail to remain discoverable when topology 7 ships? [Clarity, Quickstart §"Topology-7 forward note"]

## Docs Section Quality

- [ ] CHK037 Are the env-var docs sections written with operator-facing language (not implementer-facing)? [Clarity, Contracts §env-vars]
- [ ] CHK038 Are the docs sections specified with the same six-field shape as existing `docs/env-vars.md` entries (consistency with established convention)? [Consistency, Contracts §env-vars]

## Notes

Highest-impact open items at draft time: CHK013 + CHK017 (the per-family `BehavioralProfile` thresholds are configurable defaults that ARE NOT env vars; the spec/research treat them implicitly as a different surface, but the configuration-quality concern is whether the authoritative source is unambiguous and the relationship between env var + profile is clearly stated), CHK023 (exit-code contract for validator failure is unspecified — common gap across V16 specs), CHK027 (the `VALIDATORS` tuple membership is enforced by reviewer attention; no automated check exists). Annotation convention for runs of this checklist: `[PASS]`, `[PARTIAL]`, `[GAP]`, `[DRIFT]`, `[ACCEPTED]`. `[DRIFT]` is the right marker if the per-family threshold defaults end up duplicated in two places that disagree.
