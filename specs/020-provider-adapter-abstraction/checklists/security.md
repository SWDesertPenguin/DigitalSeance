# Security Requirements Quality Checklist: Pluggable Provider Adapter Abstraction

**Purpose**: Validate that spec 020's security requirements (key isolation, sovereignty, fail-closed, supply-chain, threat model) are specified clearly, completely, and consistently with the SACP Constitution. This checklist tests the security-requirement quality, not the implementation security.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [plan.md](../plan.md) + Constitution §3, §7, §8, §9

## API Key Isolation (Constitution §3)

- [ ] CHK001 Are the requirements for API key handling at the adapter boundary specified (encrypted-at-rest, decrypted at dispatch moment, plaintext discarded immediately)? [Completeness, Plan §"Constitution Check V1" + Data-model §ProviderRequest]
- [ ] CHK002 Is the rule "API key MUST never appear in audit logs, routing logs, or error messages" stated as a binding contract for adapters? [Gap, Constitution §3]
- [ ] CHK003 Are the requirements for `provider_message` in `CanonicalError` specified to prevent credential leakage (e.g., a 401 response body sometimes echoes the key)? [Gap, Data-model §CanonicalError]
- [ ] CHK004 Is the contract for `validate_credentials(api_key, model)` specified to disallow caching, logging, or retaining the key beyond the call's lifetime? [Gap, Contracts §"Method signatures"]

## Provider-Fallback Isolation (Constitution §3)

- [ ] CHK005 Are the requirements specifying "no transparent cross-provider fallback" stated as binding for every adapter implementation? [Completeness, Plan §"Technical Context Constraints"]
- [ ] CHK006 Is the boundary between "permitted same-provider fallback" (Anthropic API → AWS Bedrock for the same model) and "forbidden cross-provider fallback" specified at sufficient detail to apply consistently? [Clarity, Constitution §3]
- [ ] CHK007 Are the requirements for the LiteLLM adapter's existing fallback machinery documented (does v1 freeze the current fallback set, or does it expand)? [Gap, Plan §"Technical Context Constraints"]
- [ ] CHK008 Is the contract for future provider-specific adapters' fallback behavior specified (e.g., a direct-Anthropic adapter — what fallbacks are permitted)? [Gap]

## Fail-Closed Semantics (V15 + V16)

- [ ] CHK009 Are the fail-closed requirements for `SACP_PROVIDER_ADAPTER` invalid values specified (process exits with clear error listing registered names — both spec and validator concurrent)? [Consistency, Spec §FR-013 / Contracts §env-vars]
- [ ] CHK010 Are the fail-closed requirements for `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` documented for all three failure modes (unset, unreadable, unparseable)? [Completeness, Contracts §env-vars]
- [ ] CHK011 Is the fail-closed contract for adapter-init failure (e.g., LiteLLM uninstalled) specified — does the orchestrator exit cleanly or does it silently fall back to a different adapter? [Clarity, Spec §"Edge Cases"]
- [ ] CHK012 Are the requirements for `MockFixtureMissing` to raise rather than silently default specified as a binding test contract? [Completeness, Spec §FR-007 + §SC-004]
- [ ] CHK013 Is the V15 contract "pipeline-internal failures fail closed" applied to adapter-internal failures (e.g., the canonical-error mapping function itself raises)? [Gap]

## Trust-Tiered Content Model (Constitution §8)

- [ ] CHK014 Is the rule "adapters operate below the security pipeline" specified clearly enough that adapter implementers don't accidentally re-handle trust-tier content? [Clarity, Plan §"Constitution Check V10"]
- [ ] CHK015 Are the requirements for adapter handling of pre-tiered content (already sanitized, already spotlighted, already canary-placed) specified to prevent regression? [Completeness, Plan §"Constitution Check V10"]
- [ ] CHK016 Is the boundary between "adapter receives assembled prompt" and "adapter must not re-sanitize" specified? [Clarity, Plan §"Constitution Check V3"]

## Supply Chain (V11)

- [ ] CHK017 Are the requirements for LiteLLM version pinning preserved (Constitution §6.3 v1.83.0+) and referenced in the adapter spec? [Completeness, Plan §"Technical Context"]
- [ ] CHK018 Are the requirements for "no new runtime dependencies" specified as a binding contract (does the spec name a CI gate that would catch a violation)? [Verifiability, Plan §"Technical Context"]
- [ ] CHK019 Is the supply-chain motivation for the abstraction specified at sufficient detail to drive future provider-adapter scope decisions (i.e., when is a direct-Anthropic adapter justified)? [Completeness, Spec §"Overview"]
- [ ] CHK020 Are the requirements for fixture-file content documented to prevent accidental credential commit (e.g., a fixture file with real API keys)? [Gap, Contracts §mock-fixtures]

## Network Isolation

- [ ] CHK021 Is the rule "mock adapter MUST NOT make outbound network calls" specified as a binding test contract per SC-003 + US2 acceptance scenario 3? [Completeness, Spec §SC-003]
- [ ] CHK022 Are the requirements for socket-level isolation in mock-adapter tests specified (which mechanism — monkey-patch, network-blocking-scope, container-level egress block)? [Clarity, Spec §US2]
- [ ] CHK023 Are the LiteLLM adapter's network-isolation requirements (Constitution §6.3 — runs in a network-restricted container with egress limited to approved provider endpoints) preserved post-abstraction? [Completeness, Constitution §6.3]

## Audit & Forensics

- [ ] CHK024 Are the requirements for audit-log capture of adapter selection at startup specified (banner line, structured log entry)? [Completeness, Plan §"Constitution Check V5"]
- [ ] CHK025 Is the contract for `routing_log` adapter-related fields specified (which fields, populated when, scrubbing rules)? [Gap, Plan §"Constitution Check V9"]
- [ ] CHK026 Are the requirements for `original_exception` retention in `CanonicalError` documented to balance forensic detail vs log-bloat (bounded length? full traceback? scrubbing)? [Completeness, Data-model §CanonicalError]

## Sovereignty Preservation (V1 + V17)

- [ ] CHK027 Is the rule "adapter abstraction preserves all five sovereignty guarantees" verifiable per-guarantee (api-key-isolation, model-choice, fallback-isolation, budget-autonomy, prompt-privacy, exit-freedom, routing-mode-autonomy, topology-choice)? [Completeness, Plan §"Constitution Check V1"]
- [ ] CHK028 Are the requirements for transcript canonicity (V17) specified for the streaming-dispatch path (no partial response committed on mid-stream failure)? [Completeness, Contracts §stream-event-shape "Error handling"]
- [ ] CHK029 Is the contract for adapter behavior on participant exit (purge cached capabilities? clear in-flight requests? close streams cleanly) specified? [Gap]

## Threat Model Alignment

- [ ] CHK030 Is the supply-chain threat motivating this spec (single dependency carrying six normalization concerns) specified at sufficient detail to drive future hardening decisions? [Completeness, Spec §"Overview"]
- [ ] CHK031 Are the requirements for fail-closed defense against "adapter init silently succeeds with wrong adapter" specified (banner verification, test-side adapter-name assertion)? [Completeness, Quickstart §1]
- [ ] CHK032 Is the threat of fixture-file tampering addressed (file integrity at load time, schema validation, audit of fixture-file contents)? [Gap]
- [ ] CHK033 Are the requirements for protection against malicious adapter registration (e.g., a third-party package that registers an adapter under a name that collides with `litellm`) specified? [Gap]

## V19 Evidence and Judgment Markers

- [ ] CHK034 Is every factual claim in the spec (LiteLLM v1.82.7-1.82.8 supply chain compromise, Anthropic streaming event shapes, OpenAI bounded-enum cardinality) cited per V19? [Traceability, Constitution §4.14 / V19]
- [ ] CHK035 Are the judgment-call statements in the spec marked as `[JUDGMENT]` or `[ASSUMPTION]` per V19, or are they rendered as facts? [Verifiability, Constitution V19]

## Cross-Reference Integrity

- [ ] CHK036 Is the cross-reference to spec 015 §FR-003 (canonical error enumeration) accurate as of spec-write time, with a documented cadence for re-verification if spec 015 amends? [Dependency, Spec §FR-008]
- [ ] CHK037 Are the cross-references to specs 016/017/018 (which depend on this adapter abstraction) marked as binding consumers, with their FR/SC numbers cited? [Traceability, Spec §"Cross-References"]
