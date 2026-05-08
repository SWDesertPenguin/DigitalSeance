# Architecture Quality Checklist: Pluggable Provider Adapter Abstraction

**Purpose**: Validate that spec 020's interface design and abstraction quality are well-specified — does the spec define the abstraction precisely enough that two implementers would produce equivalent adapters? This checklist tests the architectural specification quality, not the implementation.
**Created**: 2026-05-08
**Feature**: [spec.md](../spec.md) + [plan.md](../plan.md) + [contracts/adapter-interface.md](../contracts/adapter-interface.md)

## Interface Definition Completeness

- [ ] CHK001 Are all seven `ProviderAdapter` abstract methods specified with full signatures (parameter names, types, return types, async vs sync)? [Completeness, Plan §"Source Code" + Contracts §"Method signatures"]
- [ ] CHK002 Is the contract for each method's failure modes documented (which exceptions are raised, which are caught and translated, which propagate)? [Completeness, Contracts §"Method signatures"]
- [ ] CHK003 Is the lifecycle of `ProviderRequest` and `ProviderResponse` instances specified (created where, mutated never, persisted where)? [Completeness, Data-model §"Frozen dataclasses"]
- [ ] CHK004 Are the responsibilities of each adapter sub-module (`dispatch.py`, `errors.py`, `streaming.py`, `capabilities.py`, `tokens.py`) defined with non-overlapping scope? [Clarity, Plan §"Source Code"]

## Abstraction Boundary Quality

- [ ] CHK005 Is the rule "no provider-native types in adapter method signatures" stated as a binding contract, or only as an aspiration? [Clarity, Spec §SC-006]
- [ ] CHK006 Is the boundary between "adapter receives" (assembled prompts) and "adapter returns" (normalized response) specified at sufficient detail to prevent leak-up of provider-specific shapes? [Clarity, Plan §"Constitution Check V10"]
- [ ] CHK007 Are the requirements for `provider_specific` opaque pass-through field's lifecycle documented (when populated, when ignored, what happens if a future adapter consumes it incorrectly)? [Completeness, Data-model §"ProviderRequest"]
- [ ] CHK008 Is the rule "the orchestrator never sees raw provider events" enforceable via a mechanical check, or does it require code review? [Measurability, Spec §"Edge Cases"]

## Registry Design

- [ ] CHK009 Is `AdapterRegistry`'s read-only-after-startup contract enforceable, or does it rely on convention? [Clarity, Plan §"Constitution Check V3" + Contracts §"Registry semantics"]
- [ ] CHK010 Are the requirements for adapter registration ordering specified (e.g., must `litellm` register before `mock`? Does order affect behavior)? [Gap]
- [ ] CHK011 Is the behavior specified when two adapter packages register under the same name (collision detection? last-write-wins? error)? [Edge Case, Contracts §"Registry semantics"]
- [ ] CHK012 Are the requirements for a deferred-import pattern documented (lazy-load adapter classes vs eager-load at startup)? [Gap]

## Singleton + Lifecycle

- [ ] CHK013 Is the `_ACTIVE_ADAPTER` slot's threading semantics specified (FastAPI single-threaded init asserted, or thread-safe init required)? [Clarity, Research §5]
- [ ] CHK014 Are the requirements for `initialize_adapter()` re-entrancy documented (called twice → raises; called from a non-startup context → raises)? [Completeness, Research §5]
- [ ] CHK015 Is the contract for `get_adapter()` in test fixtures specified (does pytest's per-test orchestrator fixture re-init the adapter, or share a process-scope adapter)? [Gap]
- [ ] CHK016 Are the requirements for adapter teardown / shutdown specified (close HTTP connections? flush caches? log shutdown)? [Gap]

## Type System

- [ ] CHK017 Is the choice of frozen dataclass over `pydantic.BaseModel` for the canonical types justified in research, or is it implicit? [Traceability, Research §1-3]
- [ ] CHK018 Are the requirements for forward-compatibility of canonical types documented (adding a field to `Capabilities` — what's the impact contract)? [Gap]
- [ ] CHK019 Is the `CanonicalErrorCategory` enum's stability contract specified (can categories be added without breaking spec 015's exhaustive `match`? renamed? deprecated)? [Gap]
- [ ] CHK020 Are the requirements for `StreamEvent` field nullability documented (which fields are populated for which event types — guaranteed contract or convention)? [Clarity, Contracts §"Field semantics by event type"]

## Cross-Module Coupling

- [ ] CHK021 Are the imports between `src/api_bridge/adapter.py`, `src/api_bridge/litellm/`, and `src/api_bridge/mock/` documented as a directed acyclic dependency? [Clarity, Plan §"Source Code"]
- [ ] CHK022 Is the rule "the adapter is the canonical home for `ProviderResponse`" specified, with the re-export shim from `src/orchestrator/types.py` documented as a backwards-compatibility measure? [Clarity, Data-model §"ProviderResponse"]
- [ ] CHK023 Are the requirements for circular-import avoidance specified (e.g., what happens if a future adapter package needs to import from another adapter package)? [Gap]

## Topology Gating

- [ ] CHK024 Is the topology-7 gate's behavior specified at sufficient detail (early return from init, raise on `get_adapter()`, banner output, log line)? [Clarity, Research §10]
- [ ] CHK025 Are the requirements documented for transitions between topologies mid-deployment (does flipping `SACP_TOPOLOGY` from 1 to 7 require a restart? is restart enforced)? [Gap]

## Concurrent Access Semantics

- [ ] CHK026 Is the capability cache's concurrent-access behavior specified (FastAPI single-threaded async event loop assumed, or explicit synchronization required)? [Clarity, Research §3]
- [ ] CHK027 Are the requirements for adapter method re-entrancy documented (can `dispatch` be called concurrently with `count_tokens`? capabilities lookup during streaming)? [Gap]
- [ ] CHK028 Is the behavior specified when streaming dispatch and non-streaming dispatch overlap on the same adapter instance (shared state, separate state, isolation guarantees)? [Gap]

## Interface Stability

- [ ] CHK029 Are the criteria for "abstraction-shaped, not LiteLLM-shaped" measurable, or does the test rely on the existence of two adapters as a proxy? [Measurability, Spec §US3]
- [ ] CHK030 Is the rule "future provider-specific adapters slot in without dispatch-path changes" specified with a precise definition of "dispatch path" (which files, which imports)? [Clarity, Spec §FR-005 + §SC-007]
- [ ] CHK031 Are the requirements for backwards-compatibility of the `ProviderAdapter` ABC documented (adding methods to the ABC — major or minor change? deprecation policy)? [Gap]

## Constitutional Alignment

- [ ] CHK032 Is the rule "adapter operates pre-bridge per §4.12" verifiable from the spec alone, or does it require reading the constitution? [Traceability, Plan §"Constitution Check V17"]
- [ ] CHK033 Are the V18 derivation-metadata requirements addressed for any artifact the adapter produces (the spec claims none — is that verifiable)? [Verifiability, Plan §"Constitution Check V18"]
- [ ] CHK034 Is the V1 sovereignty preservation specified at sufficient detail (API key isolation, model choice, budget autonomy, prompt privacy, exit freedom — each addressed)? [Completeness, Plan §"Constitution Check V1"]

## Documentation Quality

- [ ] CHK035 Is the contract documentation in `contracts/` self-contained (a reader can implement an adapter without consulting other repo files)? [Completeness, Contracts §*]
- [ ] CHK036 Are the contract docs traceable from the spec (each spec FR maps to one or more contract files)? [Traceability]
- [ ] CHK037 Is the migration path from "import litellm" to "get_adapter()" specified at sufficient detail to mechanically apply (every consumer site enumerated, every signature change documented)? [Completeness, Contracts §"Migration contract"]
