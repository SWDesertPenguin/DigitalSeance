# Contract Requirements Quality Checklist: AI Response Shaping

**Purpose**: Validate that the four `contracts/` documents (env-vars, filler-scorer-adapter, register-preset-interface, audit-events) and the spec 004 `last_embedding` hook specify their interfaces completely, unambiguously, and consistently with spec.md / data-model.md. Tests the writing, not the implementation.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md)

## Filler-Scorer Adapter Contract

- [ ] CHK001 Is the top-level `compute_filler_score()` entry point signature specified (inputs, outputs, side-effect freedom)? [Completeness, contracts/filler-scorer-adapter.md]
- [ ] CHK002 Are the three signal helper functions (hedge ratio, restatement cosine, closing pattern) defined with input shapes and return ranges? [Clarity, contracts/filler-scorer-adapter.md]
- [ ] CHK003 Is the weighted-sum aggregation formula specified, with weights summing to 1.0 per family? [Measurability, contracts/filler-scorer-adapter.md / data-model.md §BehavioralProfile]
- [ ] CHK004 Is the per-family dispatch rule specified (provider → BehavioralProfile lookup → threshold + weights)? [Completeness, contracts/filler-scorer-adapter.md]
- [ ] CHK005 Is the threshold-resolution precedence specified (env override > per-family default), with the env-var name explicit? [Clarity, contracts/filler-scorer-adapter.md / Spec §FR-002]
- [ ] CHK006 Is the retry-orchestration contract specified (when score > threshold AND budget remains, dispatch retry with `retry_delta_text`)? [Completeness, contracts/filler-scorer-adapter.md]
- [ ] CHK007 Is the per-stage cost capture rule specified (each scoring + each retry dispatch logs to routing_log)? [Coverage, contracts/filler-scorer-adapter.md]
- [ ] CHK008 Is the fail-closed contract table populated (e.g., regex error → score 0; embedding read failure → score 0; sentence-transformers unavailable → score 0)? [Completeness, contracts/filler-scorer-adapter.md]

## Register-Preset Interface Contract

- [ ] CHK009 Is the slider taxonomy (1-5: Direct, Conversational, Balanced, Technical, Academic) specified with each preset's intended register description? [Clarity, contracts/register-preset-interface.md]
- [ ] CHK010 Is each preset's `tier4_delta` text canonical (deterministic, version-controlled in source) per FR-013? [Clarity, contracts/register-preset-interface.md / FR-013]
- [ ] CHK011 Is slider 3 (Balanced) specified to emit `None` for delta (no register adjustment), distinguishing it from a tier 4 emission with empty content? [Clarity, contracts/register-preset-interface.md / Gap]
- [ ] CHK012 Are the lookup helpers (`preset_for_slider(int)` and `preset_for_name(str)`) specified with error semantics (missing slider → ValueError vs default)? [Completeness, contracts/register-preset-interface.md]

## Audit-Events Contract

- [ ] CHK013 Are the three new `admin_audit_log` action strings (`session_register_changed`, `participant_register_override_set`, `participant_register_override_cleared`) defined with payload field shapes? [Completeness, contracts/audit-events.md]
- [ ] CHK014 Is the relationship between session-level and participant-level events specified (override events do NOT emit a session event; cascade-delete on participant removal emits cleared)? [Clarity, contracts/audit-events.md / FR-015]
- [ ] CHK015 Are the actor-attribution fields specified (facilitator_id for session change; facilitator_id + target_participant_id for override events)? [Completeness, contracts/audit-events.md]
- [ ] CHK016 Are payload field-name conventions consistent between the three events (snake_case, aligned with existing `admin_audit_log` action payloads)? [Consistency, contracts/audit-events.md]

## Env-Vars Contract

- [ ] CHK017 Are the three env vars consistently specified across spec.md, contracts/env-vars.md, docs/env-vars.md, and src/config/validators.py (name, type, range, default)? [Consistency, contracts/env-vars.md]
- [ ] CHK018 Is the per-validator fail-closed semantic specified for invalid input (exit at startup with named-var error message)? [Clarity, contracts/env-vars.md / V16]
- [ ] CHK019 Is the empty-vs-unset distinction specified for `SACP_FILLER_THRESHOLD` (empty → per-family default; explicit invalid float → exit)? [Edge Case, contracts/env-vars.md]
- [ ] CHK020 Is the V16 deliverable-gate cross-link explicit (FR-014 → check_env_vars.py CI gate)? [Traceability, contracts/env-vars.md]

## Spec 004 `last_embedding` Hook

- [ ] CHK021 Is the `ConvergenceEngine.last_embedding` property specified with read-only semantics (no setter, populated by the existing convergence pipeline)? [Clarity, contracts/filler-scorer-adapter.md / data-model.md]
- [ ] CHK022 Is the `recent_embeddings(depth)` helper specified with `maxlen=3` ring buffer semantics, and is the `depth` argument constrained to ≤ ring buffer size? [Completeness, contracts/filler-scorer-adapter.md]
- [ ] CHK023 Is the no-behavior-change-to-spec-004 invariant specified (this hook adds a read API; pipeline timing and outputs unchanged)? [Consistency, plan.md / Gap]

## /me Payload Extension Contract

- [ ] CHK024 Are the three new top-level `/me` fields (`register_slider`, `register_preset`, `register_source`) specified with their value sets (slider 1-5 int, preset string ∈ five-element taxonomy, source ∈ {override, session, default})? [Completeness, contracts/register-preset-interface.md / FR-007]
- [ ] CHK025 Is the `register_source` resolution order documented at this contract layer (override → session → SACP_REGISTER_DEFAULT) consistent with FR-008? [Consistency, FR-008]
- [ ] CHK026 Is backward compatibility for existing `/me` consumers specified (additive fields only, no rename or removal)? [Coverage, FR-016 / Gap]

## Cross-Contract Consistency

- [ ] CHK027 Do the three new audit-event names (CHK013) align with the FRs that emit them (FR-009 session-change, FR-008 override pair)? [Consistency, contracts/audit-events.md]
- [ ] CHK028 Do the three new env vars (CHK017) align with the FRs that read them (FR-002, FR-005, FR-009)? [Consistency, contracts/env-vars.md]
- [ ] CHK029 Are the routing_log columns named in V14 / data-model.md (`shaping_score_ms`, etc.) consistent with the per-stage timing capture in filler-scorer-adapter.md? [Consistency, contracts/filler-scorer-adapter.md]

## Notes

- Cross-contract consistency (CHK027-CHK029) is the highest-leverage check; failures here usually indicate a stale contract that drifted from spec.md.
- The /me payload contract (CHK024-CHK026) is the only consumer-facing surface; keep it tight to avoid breaking spec 011's UI consumer at integration time.
