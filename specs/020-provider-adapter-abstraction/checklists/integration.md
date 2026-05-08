# Cross-Spec Integration Quality Checklist: Pluggable Provider Adapter Abstraction

**Purpose**: Validate that spec 020's cross-spec integration contracts (with specs 002, 015, 016, 017, 018) are specified clearly, completely, and without coupling violations. This checklist tests integration-requirement quality, not the consumer specs' implementations.
**Created**: 2026-05-08
**Feature**: [spec.md §"Cross-References to Existing Specs"](../spec.md) + [data-model.md "Cross-spec integration points"](../data-model.md)

## Spec 015 — Circuit Breaker

- [ ] CHK001 Is the cross-spec contract "spec 015's breaker consumes only `CanonicalError.category`, never the raw exception" specified as binding for both adapters? [Completeness, Spec §FR-008]
- [ ] CHK002 Is the seven-value `CanonicalErrorCategory` enum verified to exactly match spec 015 §FR-003's enumeration as of spec-write time? [Consistency, Contracts §canonical-error-mapping + Spec §FR-008]
- [ ] CHK003 Are the requirements for spec 015's existing test migration (LiteLLM exception classes → canonical categories) specified at sufficient detail to mechanically apply (which test files, which assertions)? [Clarity, Tasks §T040]
- [ ] CHK004 Is the contract for `retry_after_seconds` consumption documented (spec 015 honors it for `RATE_LIMIT`; ignored for other categories)? [Completeness, Contracts §canonical-error-mapping]
- [ ] CHK005 Is the cross-spec coupling acknowledged as the deepest in the spec set, with corresponding scrutiny applied to the mapping table's stability? [Verifiability, Spec §"Cross-References"]
- [ ] CHK006 Are the requirements for what happens when spec 015 amends its enumeration (e.g., adds an eighth category) specified — does this spec carry a forward-compatibility clause? [Gap]

## Spec 016 — Prometheus Metrics

- [ ] CHK007 Is the contract `provider_family` Prometheus label sources from `Capabilities.provider_family` specified at sufficient detail for spec 016's metric emit code to consume? [Completeness, Research §12]
- [ ] CHK008 Is the bounded-enum requirement (FR-005 cardinality control) specified with the eight-value enumeration (anthropic/openai/gemini/groq/ollama/vllm/unknown/mock)? [Completeness, Research §12]
- [ ] CHK009 Are the requirements for the `_PROVIDER_FAMILY_MAP` extension when LiteLLM adds a new provider name documented (operator-facing contract: file a fix-PR; CI catches via a test)? [Gap]
- [ ] CHK010 Is the contract for OpenAI-compatible endpoint mapping (Azure, Together, OpenRouter → `openai`) specified clearly enough to apply consistently as new endpoints emerge? [Clarity, Research §12]
- [ ] CHK011 Are the requirements for the `unknown` fallback documented (when invoked, what spec 016 metric value emits, whether an alert fires)? [Gap]

## Spec 017 — Tool-List Freshness

- [ ] CHK012 Is the cross-spec contract "spec 017 consults `Capabilities.supports_prompt_caching`" specified as binding (spec 017 must read from the adapter, not from a separate config)? [Completeness, Data-model §"Cross-spec integration points"]
- [ ] CHK013 Are the requirements for cache-control directive normalization (FR-010) specified at sufficient detail to verify the orchestrator never sees provider-native cache syntax? [Clarity, Spec §FR-010]
- [ ] CHK014 Is the contract for `prompt_cache_invalidated` (the field on spec 017 audit entries) specified — does the adapter signal whether a tool-set change actually invalidated the provider-native cache? [Completeness, Spec §"Cross-References"]
- [ ] CHK015 Are the requirements for cache-breakpoint position normalization (`cache_breakpoint_at_position` directive → provider-native syntax) specified for both Anthropic and OpenAI? [Completeness, Spec §"Edge Cases" + Data-model §ProviderRequest.cache_directives]

## Spec 018 — Deferred Tool Loading

- [ ] CHK016 Is the cross-spec contract "spec 018 consumes `count_tokens()` and `Capabilities.max_context_tokens`" specified as binding (the budget primitive is the adapter, not a separate tokenizer)? [Completeness, Data-model §"Cross-spec integration points"]
- [ ] CHK017 Is the contract for the `[NEED:]` proxy routing (when `Capabilities.supports_tool_calling=false`) specified consistently between spec 018 and this spec? [Consistency, Spec §"Cross-References" + §"Edge Cases"]
- [ ] CHK018 Are the requirements for spec 018's behavior on capability-shift (e.g., a model previously had tool_calling support but the adapter now reports false) specified — does spec 018 transition gracefully? [Edge Case, Spec §"Edge Cases"]
- [ ] CHK019 Is the audit-entry-on-unknown-tokenizer contract (FR-012) specified at sufficient detail for spec 018 to reason about budget accuracy? [Completeness, Spec §FR-012]

## Spec 002 — MCP Server (Participant Registration)

- [ ] CHK020 Is the contract "participant registration validates credentials via `adapter.validate_credentials()`" specified as binding, replacing any prior LiteLLM-direct validation? [Completeness, Spec §"Cross-References"]
- [ ] CHK021 Are the requirements for `validate_credentials`'s call surface specified at sufficient detail (which MCP tool calls trigger it, what failure mode if invalid)? [Gap]
- [ ] CHK022 Is the contract for credential validation in topology 7 (where there is no orchestrator-side adapter) specified — spec 002 has alternate validation? [Gap, Plan §"Constitution Check V12"]

## Spec 014 — Dynamic Mode Assignment (Cross-Validator Precedent)

- [ ] CHK023 Is the cross-validator pattern (mock adapter → fixtures path required) specified to mirror spec 014's `SACP_AUTO_MODE_ENABLED` ↔ `SACP_DMA_DWELL_TIME_S` precedent at the implementation-pattern level (same shape, same error-message convention)? [Consistency, Research §9]
- [ ] CHK024 Are the requirements for divergence from spec 014's pattern documented if any (e.g., the path validator needs file-readability checks; spec 014's was an integer range)? [Clarity, Research §9]

## Constitution §6.3 (LiteLLM Pin)

- [ ] CHK025 Is the requirement "LiteLLM remains pinned per Constitution §6.3 (v1.83.0+)" specified as preserved post-abstraction, with no version-pin loosening permitted? [Completeness, Plan §"Technical Context"]
- [ ] CHK026 Are the requirements for LiteLLM's network-isolation container persisting post-abstraction specified? [Completeness, Constitution §6.3 + Plan §"Constitution Check V11"]

## Constitution §3 (Sovereignty Five Guarantees)

- [ ] CHK027 Is the rule "all five sovereignty guarantees preserved" verified per-guarantee in the spec/plan, not just asserted as a single check? [Verifiability, Plan §"Constitution Check V1"]
- [ ] CHK028 Is the boundary between "permitted same-provider fallback" (Anthropic API → Bedrock for the same model) and "forbidden cross-provider fallback" specified as binding for the LiteLLM adapter (which inherits LiteLLM's fallback machinery)? [Completeness, Plan §"Technical Context Constraints"]
- [ ] CHK029 Are the requirements for routing-mode autonomy specified post-abstraction (each human controls their own AI's routing; adapter doesn't override)? [Completeness, Plan §"Constitution Check V1"]

## Spec 011 (Forward-Reference)

- [ ] CHK030 Is spec 020's lack of UI surface specified explicitly, with no spec 011 amendment needed (per memory `reminder_spec_011_amendments_at_impl_time`)? [Clarity, Tasks §"Spec 011 Forward-Reference"]
- [ ] CHK031 Are the operator-facing surfaces of this spec (env vars, banner, runbook diagnostic queries) categorized as deployment surfaces, not user-facing UI? [Consistency, Spec §V12 + V13]

## Coupling Quality

- [ ] CHK032 Are the cross-spec coupling directions documented (specs 015/016/017/018 depend on spec 020; spec 020 does NOT depend on them) — does any consumer spec inadvertently force a reverse dependency? [Verifiability]
- [ ] CHK033 Is the principle "the adapter is authoritative; consumers consult, never override" specified consistently across all five cross-spec touchpoints? [Consistency, Spec §FR-008 / FR-011 / FR-012 + Cross-Refs]

## Phase 3 Back-Fill Coherence

- [ ] CHK034 Is the "Phase 1-back-fill framing" specified consistently across the family of Phase-1-back-fill specs (015, 016, 017, 018, 019, 020)? [Consistency, Spec §"Assumptions"]
- [ ] CHK035 Are the requirements for landing-order across the back-fill family specified (does this spec block on any of 015-019, or are they independent)? [Gap]
- [ ] CHK036 Is the cross-spec status acknowledgment specified (each consumer spec's tasks may need a migration PR landed in this spec's single-PR cutover)? [Completeness, Plan §"Notes for /speckit.tasks"]

## Cross-Spec Test Strategy

- [ ] CHK037 Are the requirements for cross-spec integration smoke tests specified at sufficient detail to verify post-deployment (T070-T071 in tasks.md)? [Completeness, Tasks §T069-T071]
- [ ] CHK038 Is the contract for spec 015's test migration to canonical categories specified per Phase 5 of tasks (single-PR cutover discipline)? [Completeness, Tasks §T040]
