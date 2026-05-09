# Feature Specification: Pluggable Provider Adapter Abstraction

**Feature Branch**: `020-provider-adapter-abstraction`
**Created**: 2026-05-06
**Status**: Implemented 2026-05-08 (Phase 3 declared 2026-05-05; scaffold + clarifications resolved; LiteLLM + mock adapters + cutover landed; FR-005 architectural test green; SC-001 byte-identical regression confirmed via CI matrix)
**Input**: User description: "Pluggable provider adapter abstraction for SACP's bridge layer. SACP Phase 1 uses LiteLLM as the bridge layer for provider translation across Anthropic, OpenAI, OpenAI-compatible endpoints, Ollama, and vLLM. External dependencies at the network boundary of a multi-tenant orchestrator carry inherent supply-chain risk; SACP needs a clean abstraction layer that could swap LiteLLM for in-house provider adapters if the dependency ever needs to be replaced. Designing the interface now — without building in-house adapters — costs little and provides a swap path. The adapter interface defines SACP's internal message format (stable across all adapters) and normalizes provider-specific tool-calling formats, streaming protocols, error taxonomies, token counting, and cache-control directives at the API boundary. Phase 1 ships a single LiteLLM-backed adapter behind the interface plus a mock adapter for testing. Future phases may introduce provider-specific adapters one at a time, feature-flag gated. Phase 1 scope: interface definition, LiteLLM-backed implementation, mock for testing. Cross-references §6 of sacp-design.md (provider abstraction) and the circuit-breaker feature (error-taxonomy integration)."

## Overview

SACP's bridge layer is the single chokepoint where the orchestrator
hands a per-turn context payload to a participant's chosen provider
and receives a streamed response. Today, LiteLLM occupies that
chokepoint directly: every dispatch path imports `litellm`, every
streaming-passthrough event is a LiteLLM event, every cost-tracking
hook reads a LiteLLM-native field, every error class caught is a
LiteLLM exception type. LiteLLM is competent, comprehensive, and
production-tested — but having it directly in the dispatch surface
means SACP carries supply-chain risk equal to LiteLLM's own.

`sacp-design.md` §6 (Provider Abstraction Layer) explicitly names
the seven concerns that any bridge layer must normalize:
- §6.1 System prompt formats vary across providers and templates
  diverge for open-source models.
- §6.2 Response format normalization differs (Claude prose vs.
  GPT-4o markdown vs. local-model variance).
- §6.3 Tool access asymmetry (native function calling vs. text
  proxy).
- §6.4 Context window variance (8K to 10M tokens).
- §6.5 Streaming architecture (SSE format divergence — OpenAI
  delta strings vs. Anthropic explicit event types).
- §6.6 Error handling and resilience (rate-limit headers,
  retry-after, exponential backoff, fallback policies).
- §6.7 MCP authentication (out of bridge scope; this spec only
  covers provider-direction concerns).
- §6.8 Conversation branching (out of bridge scope; this spec
  covers per-turn dispatch only).

A single dependency carrying all six bridge-relevant concerns is
the supply-chain risk this spec exists to address. The cost of
designing the abstraction NOW — while LiteLLM is the only
implementation — is small. The cost of designing it LATER, after
SACP has accreted dispatch-path code that imports LiteLLM
directly, is large.

This spec defines a **pluggable provider adapter abstraction**:

1. A **stable internal message format** at the SACP <-> adapter
   boundary. The orchestrator never sees provider-native shapes;
   the adapter never sees orchestrator internals.
2. A **`ProviderAdapter` interface** with a small, opinionated
   method surface: `complete()`, `stream()`, `count_tokens()`,
   `validate_credentials()`, `capabilities()`,
   `normalize_error()`. Every provider-specific detail lives
   below the interface.
3. **Two implementations in v1**:
   - `LiteLLMAdapter` — production-path, byte-identically
     behavior to current LiteLLM usage. The only behavioral
     difference observable to operators is that the dispatch
     code no longer imports `litellm` directly.
   - `MockAdapter` — deterministic responses keyed on input
     fixtures, for tests that need predictable token counts,
     streaming events, and error returns without hitting a
     network or a real provider.
4. A **selection mechanism** via `SACP_PROVIDER_ADAPTER` env var
   (default `litellm`), so future provider-specific adapters
   can be introduced one at a time, feature-flag gated, without
   touching the dispatch path.
5. A **canonical error taxonomy** that spec 015's circuit
   breaker consumes via `adapter.normalize_error(exc)` — the
   adapter is the authoritative source for "is this a 5xx, a
   timeout, a 429, an auth failure, or a quality failure" so
   the breaker is not coupled to LiteLLM's exception hierarchy.

This spec is **Phase 1 scope**: interface definition + LiteLLM
adapter + mock adapter. Future provider-specific adapters
(e.g., a direct-Anthropic adapter, a direct-OpenAI adapter, an
in-house lightweight adapter) are explicitly OUT OF SCOPE here
and would each be their own spec.

## Clarifications

### Session 2026-05-08

- Q: Adapter selection scope — process-wide vs. per-participant? → A: Process-wide.
- Q: Backwards-compatibility window — single-PR cutover vs. parallel-path? → A: Single-PR cutover.
- Q: Capability negotiation location — adapter vs. participant-registration registry? → A: Adapter owns.
- Q: Token counting authority — single source vs. split inbound/outbound? → A: Adapter single source both directions.
- Q: Mock adapter fidelity — simplified vs. provider-quirk-faithful? → A: Simplified.

### Initial draft assumptions requiring confirmation

- **Adapter selection scope.** Process-wide selection via
  `SACP_PROVIDER_ADAPTER` (one adapter per orchestrator instance,
  used for all participants). Per-participant adapter selection is
  explicitly OUT OF SCOPE for this spec and would be its own future
  spec. Resolved 2026-05-08.
- **Capability negotiation.** The adapter owns capability reporting
  via `capabilities(model)`, returning a structured object
  (`supports_streaming`, `supports_tool_calling`,
  `supports_prompt_caching`, `max_context_tokens`, etc.) consulted
  at participant registration to decide e.g. whether to enable spec
  018 deferred loading or §6.3 `[NEED:]` proxy. Provider knowledge
  stays inside the adapter; no orchestrator-side capability
  registry. Resolved 2026-05-08.
- **Token counting authority.** The adapter is the single source of
  truth for both directions: inbound token counts via
  `count_tokens()` using the participant's model tokenizer, and
  outbound token counts parsed from the provider response by the
  adapter. No orchestrator-side tokenizer code; spec 018's
  deferred-loading budget primitive consumes adapter output
  directly per FR-012. Resolved 2026-05-08.
- **Mock adapter fidelity.** Simplified mock: deterministic
  responses, fake but plausibly-shaped streaming events, and an
  injectable error mode (e.g., `MockAdapter(error="5xx")`) so spec
  015's circuit breaker can be tested without network. The mock
  does NOT attempt to emulate provider-specific quirks (e.g.,
  Anthropic's exact `message_start` event sequence) — that's an
  integration-test concern handled against real providers.
  Resolved 2026-05-08.
- **Backwards-compatibility window.** Single-PR cutover: every
  `import litellm` outside the `LiteLLMAdapter` package is replaced
  with adapter calls in one PR. No parallel-old-and-new path
  window. FR-005's architectural test enforces the cutover; FR-014's
  byte-identical regression contract closes the loop in the same
  PR. Resolved 2026-05-08.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - LiteLLM-backed adapter ships behind the interface with byte-identical behavior (Priority: P1)

The dispatch path no longer imports `litellm` directly. Every call
that previously read a LiteLLM-native field, raised a LiteLLM
exception, or consumed a LiteLLM streaming event now goes through
the `ProviderAdapter` interface. The default `SACP_PROVIDER_ADAPTER=litellm`
selects the `LiteLLMAdapter`, which translates between SACP's
internal message format and LiteLLM's API. From the operator's
perspective, nothing changes: same providers supported (Anthropic,
OpenAI, OpenAI-compatible, Ollama, vLLM), same per-turn behavior,
same audit-log shape, same metrics, same costs.

**Why this priority**: P1 because this IS the swap path. Without
the interface in place, swapping LiteLLM later is a high-cost
fork-the-dispatch-path operation. With the interface in place,
swapping is "implement a new adapter, flip the env var." Shipping
the interface is the entire deliverable; the LiteLLM-backed
implementation is a no-behavior-change refactor that proves the
interface holds.

**Independent Test**: Run the full pre-feature acceptance suite
with `SACP_PROVIDER_ADAPTER=litellm` (the default). Verify every
test passes byte-identically — same response content, same audit
entries, same metric values, same per-turn timing, same cost-tracker
deltas. Separately, verify no file under `src/` outside the adapter
package imports `litellm` (architectural test).

**Acceptance Scenarios**:

1. **Given** the orchestrator is started with the default
   `SACP_PROVIDER_ADAPTER=litellm`, **When** the full pre-feature
   acceptance suite runs, **Then** every test MUST pass
   byte-identically — no test changes, no fixture changes, no
   golden-output changes (regression contract).
2. **Given** the dispatch path is refactored, **When** an
   architectural test scans the codebase for `import litellm`
   or `from litellm`, **Then** the only matching files MUST be
   inside the `LiteLLMAdapter` package. Any other file matching
   the pattern fails the test.
3. **Given** a turn dispatches via the LiteLLM-backed adapter,
   **When** a streaming response arrives, **Then** the SACP
   internal streaming-event format MUST be the same regardless
   of underlying provider — Anthropic-style and OpenAI-style
   streams MUST be normalized into a single SACP event shape
   (text deltas + tool-call deltas + finalization) before
   surfacing to the rest of the orchestrator.
4. **Given** the LiteLLM call raises an exception, **When**
   `adapter.normalize_error(exc)` is called, **Then** the
   returned canonical error type MUST match the spec 015 FR-003
   enumeration: `error_5xx`, `error_4xx`, `auth_error`,
   `rate_limit`, `timeout`, `quality_failure`, or
   `unknown`. The breaker MUST consume only the canonical type,
   never the raw exception.

---

### User Story 2 - Mock adapter enables deterministic testing without network or provider keys (Priority: P2)

Tests that need to drive specific response content, specific token
counts, specific streaming-event sequences, or specific error
modes today must either (a) hit a real provider with real
credentials (slow, flaky, expensive) or (b) monkey-patch
`litellm.completion()` (fragile, breaks on LiteLLM updates). With
the `MockAdapter`, tests configure expected outputs via fixtures
keyed on input shape and run deterministically with no network.

**Why this priority**: P2 because the production path (US1) is
correct without the mock — the mock is a testing-quality tool. But
without it, every spec that interacts with the dispatch path
(spec 015 circuit breaker, spec 016 metrics, spec 017 freshness,
spec 018 deferred loading) has to roll its own dispatch
test-double. The shared mock prevents that fragmentation and
makes those specs' tests stronger.

**Independent Test**: Set `SACP_PROVIDER_ADAPTER=mock` and run a
session whose participant config selects a fixture set. Verify
the orchestrator dispatches via the mock, that the mock returns
the configured response content and token counts, that streaming
events emerge in the configured order, and that no network call
is made (verified by socket-level test or NetworkBlockingScope).

**Acceptance Scenarios**:

1. **Given** `SACP_PROVIDER_ADAPTER=mock` and a fixture configured
   to return `("hello world", prompt_tokens=42,
   completion_tokens=10)` for any input, **When** the orchestrator
   dispatches a turn, **Then** the response MUST be `"hello world"`
   exactly, the cost tracker MUST record (42, 10) for that turn,
   and the spec 016 metric counters MUST increment with those
   exact values.
2. **Given** a fixture configured to raise a 5xx error, **When**
   the orchestrator dispatches, **Then**
   `adapter.normalize_error(raised_exc)` MUST return `error_5xx`
   and spec 015's circuit breaker MUST trip after the configured
   threshold (verified end-to-end without any real provider).
3. **Given** the mock adapter is selected, **When** any dispatch
   occurs, **Then** no outbound network call MUST be made —
   verified by a socket-level isolation harness.
4. **Given** the mock adapter is selected, **When** the orchestrator
   queries `adapter.capabilities()`, **Then** the returned object
   MUST be controllable by fixture (so tests can simulate "this
   participant is on a model without tool calling" or "this
   participant is on a 200K-context model").

---

### User Story 3 - Future provider-specific adapters slot in behind a feature flag without touching dispatch (Priority: P3)

A future spec introduces an in-house adapter (e.g., a thin direct-
Anthropic adapter that drops the LiteLLM dependency for
Anthropic-only deployments). The orchestrator selects it via
`SACP_PROVIDER_ADAPTER=anthropic_direct`. Every dispatch-path
file is unchanged — the new adapter conforms to the same
interface and slots in. The feature-flag gating means operators
can run the new adapter alongside the LiteLLM adapter (different
processes) and compare behavior before committing.

**Why this priority**: P3 because no future adapter ships in this
spec — US3 is forward-compatibility verification, not a deliverable.
But verifying the interface CAN take a second adapter (via the
mock) is essential to confirm the interface is genuinely
abstraction-shaped and not LiteLLM-shaped.

**Independent Test**: Confirm the interface is implementable by
two unrelated adapters (LiteLLM + mock) without dispatch-path
changes. Confirm `SACP_PROVIDER_ADAPTER=mock` selects the mock
and `=litellm` selects LiteLLM. Confirm an invalid value
fails-closed at startup.

**Acceptance Scenarios**:

1. **Given** the adapter interface is defined, **When** both the
   LiteLLM and mock adapters are implemented, **Then** the
   interface MUST be implementable by both WITHOUT either
   adapter's implementation requiring changes to the dispatch
   path or the orchestrator's per-turn loop.
2. **Given** `SACP_PROVIDER_ADAPTER` is set to a name not
   matching any registered adapter, **When** the orchestrator
   starts, **Then** the process MUST exit with a clear error
   message naming the offending value AND listing the registered
   adapter names (V16 fail-closed).
3. **Given** a future adapter is added by registering it in the
   adapter registry, **When** the orchestrator starts with
   `SACP_PROVIDER_ADAPTER=future_name`, **Then** the orchestrator
   MUST instantiate the new adapter via the registry without any
   dispatch-path file change.
4. **Given** the LiteLLM adapter and the mock adapter coexist in
   the same process at registration time, **When** the
   orchestrator starts, **Then** both adapters MUST be importable
   without dependency conflicts and only the env-var-selected
   adapter MUST be instantiated for dispatch.

---

### Edge Cases

- **Adapter raises during initialization (e.g., LiteLLM import
  fails because LiteLLM is uninstalled).** Startup MUST fail
  with a clear error naming the adapter and the underlying
  cause. Falling back to a different adapter silently would
  defeat the explicit-selection semantics.
- **Two adapters disagree on canonical error mapping for the same
  exception.** The adapter is authoritative for its own error
  taxonomy — there is no cross-adapter normalization step. Spec
  015 trusts the adapter's `normalize_error()` output.
- **Adapter's `capabilities()` returns
  `supports_tool_calling=false` for a model SACP previously
  treated as supporting tool calling.** Spec 018 defers to the
  adapter's reported capability; the participant gets `[NEED:]`
  proxy treatment instead. This is a behavior-change boundary
  — operators upgrading providers may see capability shifts.
- **Streaming event order from the adapter does not match the
  orchestrator's expected sequence.** The adapter is responsible
  for normalizing — if Provider X delivers events out of
  causal order, the adapter buffers and reorders before
  emitting SACP events. The orchestrator never sees raw provider
  events.
- **Cache-control directive (provider-native prompt caching)
  semantics differ between providers.** The adapter normalizes
  to a single `cache_breakpoint_at_position` directive that the
  orchestrator passes; the adapter translates to provider-native
  syntax (Anthropic `cache_control`, OpenAI prefix-cache markers,
  etc.). The orchestrator does not know provider-native cache
  syntax exists.
- **Adapter is upgraded mid-deployment.** Adapter is process-wide
  and chosen at startup; mid-process adapter swap is OUT OF
  SCOPE. Operator restarts the orchestrator to swap.
- **Mock adapter receives a request without a configured
  fixture.** Mock MUST raise a clear `MockFixtureMissing`
  exception that names the missing fixture key, not silently
  return a default. Tests must declare every dispatch they
  expect.
- **Token counting requires a model the adapter doesn't
  recognize** (custom local model). Adapter MUST return a
  conservative-overestimate token count (using a generic
  tokenizer) AND emit an audit entry warning the operator. Cost
  tracking will be slightly inflated; that is the safe direction
  for budget enforcement.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A `ProviderAdapter` interface MUST be defined as the
  sole boundary between the dispatch path and any underlying
  provider library. The interface MUST contain at minimum:
  `complete(request) -> Response`,
  `stream(request) -> AsyncIterator[StreamEvent]`,
  `count_tokens(messages, model) -> int`,
  `validate_credentials(api_key, model) -> ValidationResult`,
  `capabilities(model) -> Capabilities`,
  `normalize_error(exc) -> CanonicalError`.
- **FR-002**: The orchestrator MUST select an adapter at startup
  via `SACP_PROVIDER_ADAPTER` (default `litellm`). The selection
  MUST be process-wide and immutable for the process lifetime.
- **FR-003**: An adapter registry MUST map env-var values to
  adapter classes. Adapter implementations register themselves
  in the registry at module import time. The registry MUST be
  read-only after orchestrator startup.
- **FR-004**: The `LiteLLMAdapter` MUST be the v1 default and MUST
  produce behavior byte-identical to the pre-feature LiteLLM
  usage — same providers supported, same per-turn outcomes,
  same audit-log shape, same metric values, same cost-tracker
  results.
- **FR-005**: No file under `src/` outside the
  `LiteLLMAdapter` package may import `litellm` or `from litellm`.
  An architectural test MUST enforce this.
- **FR-006**: The `MockAdapter` MUST be selectable via
  `SACP_PROVIDER_ADAPTER=mock` and MUST return deterministic
  responses keyed on input fixtures. The mock MUST support
  injectable error modes covering every entry of the spec 015
  FR-003 canonical error taxonomy.
- **FR-007**: The mock adapter MUST emit a `MockFixtureMissing`
  exception (not a default response) when an unconfigured input
  is dispatched, naming the missing fixture key.
- **FR-008**: Every adapter MUST implement `normalize_error(exc)`
  to return a canonical error matching the spec 015 FR-003
  enumeration. Spec 015's circuit breaker MUST consume only the
  canonical type, never the raw exception. The adapter is the
  authoritative source for "is this a 5xx vs. timeout vs. auth
  failure."
- **FR-009**: Streaming events surfaced from the adapter MUST
  follow a single SACP-internal event shape covering: text
  deltas, tool-call deltas, finalization. Provider-specific
  event shapes MUST NOT leak past the adapter boundary.
- **FR-010**: The adapter MUST normalize provider-specific
  cache-control directives. The orchestrator passes a generic
  `cache_breakpoint_at_position` (or equivalent) directive; the
  adapter translates to provider-native syntax. The orchestrator
  has no awareness of provider-native cache control.
- **FR-011**: `capabilities(model)` MUST return a structured
  object including at minimum:
  `supports_streaming, supports_tool_calling,
  supports_prompt_caching, max_context_tokens,
  tokenizer_name, recommended_temperature_range`. Specs 015,
  016, 017, and 018 MUST consult `capabilities()` for any
  behavior gated on model capability.
- **FR-012**: `count_tokens()` MUST use the participant's model
  tokenizer when known and a conservative-overestimate generic
  tokenizer when not, with an audit entry on the
  unknown-tokenizer path. The adapter MUST be the single source
  of truth for inbound token counts.
- **FR-013**: The two new env vars (`SACP_PROVIDER_ADAPTER`,
  `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`) MUST have
  validator functions in `src/config/validators.py` registered
  in the `VALIDATORS` tuple, and corresponding sections in
  `docs/env-vars.md` with the six standard fields BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable gate).
- **FR-014**: When `SACP_PROVIDER_ADAPTER=litellm` (the default)
  and `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` is unset, the
  orchestrator's pre-feature behavior MUST be byte-identical:
  same dispatched messages, same responses, same audit-log
  content, same metric values, same cost-tracker outcomes.
- **FR-015**: Mid-process adapter swap is OUT OF SCOPE. Adapter
  selection at startup is final for the process lifetime.

### Key Entities

- **ProviderAdapter** (interface) — the abstract base class
  implemented by `LiteLLMAdapter` and `MockAdapter`. Methods per
  FR-001.
- **AdapterRegistry** (process-scope) — maps env-var values to
  adapter classes. Read-only after startup.
- **Capabilities** — structured object returned by
  `capabilities(model)`: `supports_streaming, supports_tool_calling,
  supports_prompt_caching, max_context_tokens, tokenizer_name,
  recommended_temperature_range`.
- **CanonicalError** — enumeration matching spec 015 FR-003:
  `error_5xx, error_4xx, auth_error, rate_limit, timeout,
  quality_failure, unknown`.
- **StreamEvent** — SACP-internal streaming event shape covering
  text-delta, tool-call-delta, finalization. Provider-native
  shapes MUST translate into this.
- **MockFixtureSet** (mock-only) — collection of input-pattern →
  expected-response mappings loaded from
  `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With `SACP_PROVIDER_ADAPTER=litellm` (default), the
  full pre-feature acceptance suite passes byte-identically —
  verified in CI on the spec's PR.
- **SC-002**: An architectural test asserts no file outside
  `LiteLLMAdapter` package imports `litellm` — verified in CI
  on every PR going forward.
- **SC-003**: Spec 015's circuit-breaker tests pass using the
  mock adapter's injectable error modes — verified by porting
  one or more spec 015 tests to use `SACP_PROVIDER_ADAPTER=mock`
  and asserting equivalent behavior.
- **SC-004**: The mock adapter raises `MockFixtureMissing` on
  unconfigured dispatch — verified by a test that drives an
  unconfigured input and asserts the exception with its
  fixture-key payload.
- **SC-005**: Adapter-selection failure (`SACP_PROVIDER_ADAPTER`
  set to a non-registered value) causes startup exit with a
  clear error listing all registered adapter names — verified
  by a test that drives the failure and asserts the exit
  message.
- **SC-006**: Provider-native imports do not leak past the
  adapter boundary — verified by `StreamEvent`,
  `CanonicalError`, and `Capabilities` being defined in SACP
  internal modules with no provider-native types in their
  signatures.
- **SC-007**: Two unrelated adapters (LiteLLM + mock) coexist
  without dispatch-path changes — verified by the dispatch-path
  files being unchanged (modulo import statements pointing at
  the registry, not at LiteLLM) when both adapters are
  registered.
- **SC-008**: With any env var set to an invalid value, the
  orchestrator process exits at startup with a clear error
  message naming the offending var (V16 fail-closed gate
  observed in CI).

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

This feature **applies to topologies 1-6** (orchestrator-driven
topologies). The bridge layer is the orchestrator's component
that talks to providers; topologies 1-6 all run dispatch through
the orchestrator.

This feature is **NOT applicable to topology 7 (MCP-to-MCP, Phase
3+)**. In topology 7 each participant's client (Claude Desktop,
ChatGPT app) talks to its own provider directly; there is no
orchestrator-side bridge layer to abstract. Per V12: any
topology-7 deployment MUST recognize that this spec's adapter
abstraction does not apply.

### V13 — Use Case Coverage

This feature is **internal architecture** rather than user-facing
behavior. It serves all four use cases by enabling future
provider-implementation flexibility:

- §1 Distributed Software Collaboration: future direct-Anthropic
  or direct-OpenAI adapters could land here for software-team
  deployments using a single provider.
- §2 Research Co-authorship: research deployments often use
  diverse provider mixes; the LiteLLM adapter remains the right
  fit for v1 and beyond.
- §3 Consulting Engagement: consultants requiring stricter
  supply-chain controls can swap to an in-house adapter.
- §4 Open Source Coordination: contributor diversity argues for
  flexibility — the abstraction is what makes diversity
  achievable.

No use case is the priority driver — this is foundational
architecture.

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable contracts. This
spec contributes two budgets:

- **Adapter-call overhead per dispatch**: The adapter call layer
  MUST add no more than the V14 per-stage budget tolerance to
  the dispatch path versus the pre-feature direct-LiteLLM call.
  In practice this is a single virtual-method dispatch — the
  abstraction MUST NOT introduce buffering, copying, or
  serialization beyond what LiteLLM already does. Budget
  enforcement: per-dispatch timing captured in routing log on a
  sample basis.
- **`normalize_error()` execution**: Constant-time (`O(1)`).
  Pattern matching exception types or status codes; no I/O,
  no allocation beyond the returned canonical-error object.
  Budget enforcement: spec 015's audit entries record the
  normalize-error duration when the breaker increments.

## Configuration (V16) — New Env Vars

Two new env vars are introduced. Each MUST have type, valid range,
and fail-closed semantics documented in `docs/env-vars.md` BEFORE
`/speckit.tasks` is run for this spec (per V16 deliverable gate).

### `SACP_PROVIDER_ADAPTER`

- **Intended type**: string, adapter name from the registry
- **Intended valid range**: any name registered in
  `AdapterRegistry`. v1 ships `litellm` and `mock`; future
  adapters add their names.
- **Fail-closed semantics**: unset means `litellm` (default).
  Set to a non-registered value MUST cause startup exit per V16
  with an error message listing all registered names.

### `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`

- **Intended type**: filesystem path to a fixtures file
  (JSON or YAML; final format settled in `/speckit.plan`)
- **Intended valid range**: must be a readable file path with
  valid fixture content.
- **Fail-closed semantics**: unset is allowed when
  `SACP_PROVIDER_ADAPTER != mock`. When the mock is selected and
  the path is unset, startup MUST exit with a clear error.
  Unparseable fixtures content MUST cause startup exit.

## Cross-References to Existing Specs and Design Docs

- **`sacp-design.md` §6 (Provider Abstraction Layer)** — the
  entire chapter motivates this spec. §6.1–§6.6 each identify
  a normalization concern the adapter interface owns; §6.7–§6.8
  are out of bridge scope.
- **`sacp-design.md` §6.1 (System Prompt Architecture)** — the
  4-tier delta-only system prompt is computed at the orchestrator;
  the adapter receives the assembled prompt and translates to
  provider-native template format.
- **`sacp-design.md` §6.2 (Response Format Normalization)** —
  format strip / whitespace normalize / truncation pipeline runs
  AT the orchestrator, AFTER the adapter has surfaced a
  normalized response.
- **`sacp-design.md` §6.3 (Tool Access Asymmetry)** — the
  `[NEED:]` proxy is for participants whose adapter
  `capabilities().supports_tool_calling=false`. FR-011 makes
  this routing explicit.
- **`sacp-design.md` §6.5 (Streaming Architecture)** — the
  split-stream accumulator consumes adapter `StreamEvent`s, not
  provider-native events (FR-009).
- **`sacp-design.md` §6.6 (Error Handling and Resilience)** —
  the canonical error taxonomy (FR-008) provides the input to
  spec 015's circuit breaker; LiteLLM's specific cooldown
  features remain inside the LiteLLM adapter.
- **Constitution §3 (Sovereignty)** — adapter abstraction
  preserves all five sovereignty guarantees (no transparent
  cross-identity provider fallback per FR-008 + spec 015 FR-011).
- **Spec 002 (mcp-server)** — participant registration validates
  credentials via `adapter.validate_credentials()` (FR-001).
- **Spec 015 (provider-failure-detection)** — the circuit
  breaker consumes `adapter.normalize_error()` output as its
  authoritative failure-kind source. This is the deepest
  cross-spec coupling.
- **Spec 016 (prometheus-metrics)** — `provider_family` label
  values come from the adapter's `capabilities()` provider
  metadata. The adapter is the authoritative source for the
  bounded enumeration spec 016 FR-005 requires.
- **Spec 017 (tool-list-freshness)** — cache-control directive
  normalization (FR-010) interacts with the
  `prompt_cache_invalidated` field on spec 017 audit entries:
  the adapter knows whether a tool-set change actually
  invalidated the provider-native cache.
- **Spec 018 (deferred-tool-loading)** — token counting via
  `adapter.count_tokens()` (FR-012) is the budget primitive
  spec 018's partition policy depends on. The
  participant-tokenizer-aware count is the spec 018 assumption
  that this spec satisfies.

## Assumptions

- LiteLLM remains the v1 production-path implementation. No
  dependency removal is in scope; this spec adds an interface
  layer above LiteLLM.
- The adapter interface is small enough that future adapters
  can be reasonably implemented (under ~1k LoC each for a
  single-provider adapter). If the interface grows large enough
  to make this implausible, the abstraction has failed its
  purpose; this is a soft architectural constraint enforced
  during `/speckit.plan`.
- Provider-specific extensions (e.g., Anthropic's prompt-caching
  quirks, OpenAI's structured-outputs JSON schema) are
  expressible through the generic interface plus a
  `provider_specific` opaque pass-through field on the request
  payload. The opaque field MUST be unused by the LiteLLM
  adapter in v1; it is a forward-compatibility hook.
- The fixture format for `MockAdapter` is settled in
  `/speckit.plan`. JSON or YAML are both reasonable; consistency
  with existing test-fixture patterns in the repo is the
  deciding factor.
- The `LiteLLMAdapter` does not pin a specific LiteLLM version
  beyond what the orchestrator already requires. Pinning is a
  dependency-management concern, not a spec concern.
- Future provider-specific adapters are explicitly OUT OF SCOPE
  here. Each future adapter is its own spec, gated by feature
  flag (`SACP_PROVIDER_ADAPTER=<name>`), and ships only when
  the operator opts in.
- "Phase 1 scope" in the user description is interpreted as the
  same back-fill framing as specs 015, 016, 017, 018, 019 —
  Phase 1 closed 2026-04-20 per memory; this spec retroactively
  adds the interface layer that Phase 1 should arguably have
  shipped with. Confirmation pending across the family of
  Phase-1-back-fill specs.
- Five draft-assumption clarifications resolved 2026-05-08; spec
  status advanced to Clarified. `/speckit.plan` and `/speckit.tasks`
  remain deferred to user invocation.
