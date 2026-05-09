# Implementation Plan: Pluggable Provider Adapter Abstraction

**Branch**: `020-provider-adapter-abstraction` | **Date**: 2026-05-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/020-provider-adapter-abstraction/spec.md`

## Summary

Refactor the existing `src/api_bridge/` package into a `ProviderAdapter` interface plus two implementations (`LiteLLMAdapter` for production, `MockAdapter` for testing) selected at startup via `SACP_PROVIDER_ADAPTER`. The dispatch path stops importing `litellm` directly — every call routes through the adapter interface, normalized into SACP-internal types (`StreamEvent`, `CanonicalError`, `Capabilities`). FR-005 is enforced by an architectural test that scans `src/` for `import litellm` outside the `LiteLLMAdapter` package. FR-014 requires byte-identical regression behavior with the default `SACP_PROVIDER_ADAPTER=litellm`. Two new env vars + V16 validators + `docs/env-vars.md` sections land before `/speckit.tasks`.

Technical approach: introduce `src/api_bridge/adapter.py` holding the `ProviderAdapter` ABC and a process-scope `AdapterRegistry` (read-only after startup per FR-003). Restructure existing dispatch code into `src/api_bridge/litellm/` package — `dispatch.py` (current `provider.py` body), `errors.py` (canonical-error mapping), `streaming.py` (provider-event-to-SACP-event normalization), `tokens.py` (re-exports `tokenizer.py`'s logic behind the adapter method), `capabilities.py` (consults LiteLLM model metadata + `model_limits.py`). Add `src/api_bridge/mock/` package — `adapter.py` (deterministic dispatch), `fixtures.py` (fixture-set loader), `errors.py` (injectable canonical-error modes). The cutover is a single PR per the resolved clarification: every consumer of `from src.api_bridge.provider import dispatch_with_retry` migrates to `adapter = get_adapter(); await adapter.dispatch_with_retry(...)`. Spec 015's circuit breaker swaps from catching LiteLLM exception classes to consuming `adapter.normalize_error(exc)` per FR-008.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. **No new runtime dependencies.** LiteLLM remains the v1 production-path implementation per spec assumption — pinned per Constitution §6.3 (v1.83.0+ post supply-chain compromise advisory). The mock adapter has zero third-party dependencies.
**Storage**: PostgreSQL 16. **No schema changes.** No new tables, no new columns, no migration. The adapter abstraction is internal-architecture refactor only; persistence shapes (`messages`, `routing_log`, `admin_audit_log`, `convergence_log`, `security_events`) are unchanged.
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). Architectural test (`tests/test_020_no_litellm_imports.py`) scans `src/` for `import litellm` / `from litellm` outside the `src/api_bridge/litellm/` package per FR-005. Pre-feature acceptance tests MUST pass byte-identically with `SACP_PROVIDER_ADAPTER=litellm` (default) per SC-001 regression contract. Mock-adapter test path (`SACP_PROVIDER_ADAPTER=mock`) runs spec 015 circuit-breaker tests deterministically without network per SC-003.
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm). Server-side only — no client-visible surface change. The adapter selection is an operator-deployment knob, not a participant-runtime choice.
**Project Type**: Web service (single project, existing layout — `src/` + `tests/`). Refactor stays within the existing `src/api_bridge/` package; no top-level package added.
**Performance Goals**:
- **Adapter-call overhead per dispatch** (V14 budget 1): one virtual-method dispatch over the existing direct call. Spec §"Performance Budgets" caps the abstraction at "no more than the V14 per-stage budget tolerance" — operationally, this means no buffering, copying, or serialization beyond what LiteLLM already does. Per-dispatch timing captured in `routing_log` on a sample basis (existing `@with_stage_timing` pattern).
- **`normalize_error()` execution** (V14 budget 2): constant-time `O(1)`. Pattern matching exception types or status codes; no I/O, no allocation beyond the returned `CanonicalError` object. Spec 015's audit entries record the `normalize_error` duration when the breaker increments.
- **`count_tokens()` execution**: bounded by tokenizer load + token-encoding cost — same as existing `src/api_bridge/tokenizer.py` behavior. No new budget; inherits the existing tokenizer's cost profile.
**Constraints**:
- **Refactor — not a feature.** No new user-visible behavior; FR-014 requires byte-identical regression with the default adapter. Any observable behavior change vs. pre-feature LiteLLM dispatch is a defect.
- **Single-PR cutover** (clarification 2026-05-08): no parallel-old-and-new path window. Every consumer of `src.api_bridge.provider` migrates to the adapter interface in one PR; FR-005's architectural test enforces no `import litellm` outside the LiteLLM adapter package.
- **Process-wide adapter selection** (clarification 2026-05-08): one adapter per orchestrator instance, immutable for process lifetime per FR-002. Mid-process swap is OUT OF SCOPE per FR-015.
- **Adapter owns capabilities** (clarification 2026-05-08): no orchestrator-side capability registry. `capabilities(model)` is the authoritative source per FR-011; specs 015/016/017/018 consult it.
- **Adapter owns tokens both directions** (clarification 2026-05-08): no orchestrator-side tokenizer code; spec 018 deferred-loading consumes adapter output per FR-012.
- **Mock is shape-conforming, not quirk-faithful** (clarification 2026-05-08): the mock returns deterministic responses keyed on input fixtures; provider-quirk emulation is an integration-test concern handled against real providers.
- **No transparent cross-provider failover** (Constitution §3 sovereignty + spec 015 FR-011): the adapter MUST NOT transparently fall back from one participant-chosen provider to another. Same-provider fallbacks (e.g., Anthropic API → AWS Bedrock for the same Claude model) are permitted only when the underlying model identity is preserved. The LiteLLM adapter inherits LiteLLM's existing fallback machinery; the v1 cutover MUST NOT widen the fallback surface beyond what current code already permits.
- 25/5 coding standards (Constitution §6.10).
- V15 fail-closed: invalid env vars exit at startup before binding ports; `SACP_PROVIDER_ADAPTER` set to a non-registered value, or `SACP_PROVIDER_ADAPTER=mock` with `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` unset/unreadable/unparseable, exits with a clear error.
**Scale/Scope**: Phase 1+2+3 ceiling 5 participants per session. Per-turn dispatch path adds one virtual-method dispatch (negligible). The adapter package replaces ~450 LoC of existing `src/api_bridge/` with refactored modules; the mock adapter adds ~150 LoC.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | API key isolation preserved — keys still decrypt at dispatch moment and discard immediately (existing `_decrypt_key` pattern moves into the LiteLLM adapter unchanged). Model choice independence preserved — adapter selection is operator-deployment scope, not participant-routing scope. Provider-fallback isolation preserved per Technical Context constraint above. Budget autonomy unchanged — cost tracking still reads adapter output, not pooled across participants. Prompt privacy unchanged — adapters receive assembled per-participant prompts, never cross-leak. |
| **V2 No cross-phase leakage** | PASS | Phase-1-back-fill scope per spec assumption. The adapter abstraction is foundational architecture that Phase 1 should arguably have shipped with; no future-phase capability is consumed. Specs 015/016/017/018 (also Phase-1-back-fill) consume the abstraction. |
| **V3 Security hierarchy** | PASS | Refactor preserves the existing security pipeline at the orchestrator layer — adapter sits below the security pipeline, never above it. Trust-tiered content model (§8) is unaffected; adapters receive already-tiered prompts. |
| **V4 Facilitator powers bounded** | PASS | No facilitator surface change. Adapter selection is operator-deployment knob (env var), not a runtime facilitator tool. |
| **V5 Transparency** | PASS | Per-dispatch timing + canonical-error mapping captured in `routing_log` (FR-009 + V14 budget 2). Adapter selection captured at startup banner (existing config-validation log pattern) so operators can verify which adapter is active. |
| **V6 Graceful degradation** | PASS | `normalize_error()` mapping preserves existing degradation semantics — every LiteLLM exception class maps to a canonical category (5xx, 4xx, auth_error, rate_limit, timeout, quality_failure, unknown) per FR-008. Spec 015 circuit breaker continues to trip on canonical kinds without behavior change. Adapter init failure (e.g., LiteLLM uninstalled) MUST exit cleanly per spec edge case — falling back silently to a different adapter would defeat explicit-selection semantics (Constitution §3 sovereignty). |
| **V7 Coding standards** | PASS | Adapter ABC + two implementations stay within 25/5 limits. The `LiteLLMAdapter` is a thin wrapper over existing dispatch helpers (already 25/5 compliant); restructuring splits `provider.py` (325 lines) across `dispatch.py` + `errors.py` + `streaming.py` + `capabilities.py` for module-level cohesion, no per-function growth. |
| **V8 Data security** | PASS | No new data tier. API keys remain Tier 1 (secrets) — encrypted at rest, decrypted at dispatch moment, plaintext discarded after the adapter call returns. Mock-adapter fixtures contain no real credentials per V11 (mock fixture format documented in `contracts/mock-fixtures.md`). |
| **V9 Log integrity** | PASS | No log table changes. The existing `routing_log` and `admin_audit_log` schemas accept the canonical-error category in existing fields; no new event types required. |
| **V10 AI security pipeline** | PASS | The security pipeline (sanitization, spotlighting, output validation, jailbreak detection per §8) operates at the orchestrator layer — above the adapter boundary. Adapters receive pre-sanitized assembled prompts and surface raw provider responses up to the security pipeline. Refactor introduces no new content-handling surface. |
| **V11 Supply chain** | PASS | No new dependencies. LiteLLM continues at the same pin (Constitution §6.3); the adapter abstraction REDUCES supply-chain risk by isolating LiteLLM behind a stable interface that future swap-in adapters can implement. Mock-adapter fixtures land as test data under `tests/fixtures/mock_adapter/`; format documented in `contracts/mock-fixtures.md`. |
| **V12 Topology compatibility** | PASS | Spec §V12 marks the feature applicable to topologies 1-6 (orchestrator-driven dispatch); topology 7 (MCP-to-MCP) has no orchestrator-side bridge layer to abstract. Same forward-document pattern as specs 014/021 — controller-side init checks `SACP_TOPOLOGY` and skips adapter registration when topology 7 is active. |
| **V13 Use case coverage** | PASS | Spec §V13 acknowledges the feature is internal architecture serving all four use cases by enabling future provider-implementation flexibility. No single use case drives the priority. |
| **V14 Performance budgets** | PASS | Two V14 budgets in spec §"Performance Budgets" (adapter-call overhead per dispatch <= V14 per-stage tolerance, `normalize_error()` `O(1)`) with `routing_log` instrumentation reusing the existing `@with_stage_timing` pattern. |
| **V15 Fail-closed** | PASS | Invalid env vars exit at startup (FR-013); adapter init failure exits at startup (spec edge case "Adapter raises during initialization"); mock-adapter `MockFixtureMissing` raises rather than silently returning a default per FR-007. |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Two new env vars (`SACP_PROVIDER_ADAPTER`, `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`) require validators in `src/config/validators.py` (registered in `VALIDATORS` tuple) plus `docs/env-vars.md` sections with the six standard fields BEFORE `/speckit.tasks` (FR-013). Cross-validator dependency: when `SACP_PROVIDER_ADAPTER=mock`, `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` MUST be set and readable; when adapter is `litellm`, the fixtures-path var is ignored. Contract in [contracts/env-vars.md](./contracts/env-vars.md). |
| **V17 Transcript canonicity** | PASS | Adapter operates pre-bridge per §4.12 (per-participant pre-bridge processing only). The shared transcript is unaffected — adapter receives an already-assembled per-participant payload and returns a normalized response that the orchestrator commits to the canonical transcript. No transcript mutation, compression, or rewrite. |
| **V18 Derived artifacts traceable** | PASS | The adapter does not produce derived artifacts (no summaries, no embeddings, no compressed views). `StreamEvent` and `CanonicalError` are translation primitives, not derived artifacts in the §7 sense. No derivation-metadata requirement applies. |
| **V19 Evidence and judgment markers** | PASS | Spec uses `[NEEDS CLARIFICATION]` markers (resolved 2026-05-08) per §4.14; no unsourced factual claims. The "LiteLLM is competent, comprehensive, and production-tested" claim is a judgment that the spec frames as a tradeoff statement, not as a third-party-behavior fact. |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/020-provider-adapter-abstraction/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (env-vars, adapter-interface,
│                        #                  canonical-error mapping, stream-event
│                        #                  shape, mock-fixtures)
├── checklists/          # Phase 1 output (requirements quality checklist)
├── spec.md              # Feature spec (input — not modified here)
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (repository root)

```text
src/api_bridge/                        # existing package — restructured, not replaced
├── __init__.py                        # re-export `get_adapter()` helper for consumers
├── adapter.py                         # NEW — `ProviderAdapter` ABC + `AdapterRegistry`
│                                      #       process-scope singleton + `get_adapter()`
│                                      #       factory + canonical types `StreamEvent`,
│                                      #       `CanonicalError`, `Capabilities`,
│                                      #       `ProviderRequest`, `ProviderResponse`
├── litellm/                           # NEW package — LiteLLM-backed adapter; the only
│   │                                  #               place `import litellm` is permitted
│   ├── __init__.py                    # registers `LiteLLMAdapter` with the registry
│   │                                  #     under the name `"litellm"`
│   ├── adapter.py                     # NEW — `LiteLLMAdapter` class implementing the ABC;
│   │                                  #       methods delegate to dispatch.py / errors.py /
│   │                                  #       streaming.py / capabilities.py
│   ├── dispatch.py                    # MOVED from existing provider.py — request payload,
│   │                                  #       LiteLLM call, response extraction
│   ├── errors.py                      # NEW — `_normalize_error()` mapping LiteLLM
│   │                                  #       exception classes to `CanonicalError`
│   ├── streaming.py                   # NEW — provider-stream-event to SACP `StreamEvent`
│   │                                  #       normalization (text deltas, tool-call
│   │                                  #       deltas, finalization)
│   ├── capabilities.py                # NEW — `_capabilities(model)` consulting LiteLLM
│   │                                  #       model metadata + model_limits.py
│   └── tokens.py                      # NEW — `_count_tokens()` reusing tokenizer.py
├── mock/                              # NEW package — deterministic test adapter
│   ├── __init__.py                    # registers `MockAdapter` under name `"mock"`
│   ├── adapter.py                     # NEW — `MockAdapter` class implementing the ABC
│   ├── fixtures.py                    # NEW — fixture-set loader (path resolution from
│   │                                  #       `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`,
│   │                                  #       JSON parse, schema validation)
│   ├── errors.py                      # NEW — `MockFixtureMissing` exception class +
│   │                                  #       canonical-error injection helpers
│   └── streaming.py                   # NEW — synthesizes plausibly-shaped SACP
│                                      #       `StreamEvent` sequences from fixture data
├── caching.py                         # (existing) — unchanged; `CacheDirectives` becomes
│                                      #              an adapter input parameter
├── format.py                          # (existing) — unchanged; `to_provider_messages`
│                                      #              still translates orchestrator
│                                      #              messages to provider message dicts
├── list_models.py                     # (existing) — unchanged; consumed by MCP tool
├── model_limits.py                    # (existing) — unchanged; backs LiteLLM adapter's
│                                      #              `capabilities(model)` for max tokens
├── tokenizer.py                       # (existing) — unchanged; backs LiteLLM adapter's
│                                      #              `count_tokens()`
└── provider.py                        # DELETED — body moves to litellm/dispatch.py;
                                       #           any external `from src.api_bridge.provider`
                                       #           import becomes `get_adapter().dispatch_with_retry(...)`

src/orchestrator/loop.py               # (existing) — replace `from src.api_bridge.provider
                                       #              import dispatch_with_retry` with
                                       #              `from src.api_bridge.adapter import
                                       #              get_adapter`; per-turn dispatch reads
                                       #              `adapter = get_adapter()` once at
                                       #              startup, calls `adapter.dispatch_with_retry`
                                       #              at the same call sites

src/orchestrator/circuit_breaker.py    # (existing) — replace LiteLLM exception class
                                       #              catches with `adapter.normalize_error(exc)`
                                       #              consumption per FR-008

src/orchestrator/types.py              # (existing) — `ProviderResponse` becomes a re-export
                                       #              from `src.api_bridge.adapter` (the
                                       #              canonical type lives there now)

src/config/validators.py               # add two validators for the new SACP_* env vars

tests/
├── test_020_adapter_registry.py            # NEW — US3 (P3) — registry mapping; invalid
│                                            #                  adapter name fails-closed
│                                            #                  per FR-002 + SC-005
├── test_020_litellm_adapter_regression.py  # NEW — US1 (P1) — full pre-feature acceptance
│                                            #                  suite passes byte-identically
│                                            #                  with `SACP_PROVIDER_ADAPTER=
│                                            #                  litellm` per SC-001
├── test_020_no_litellm_imports.py          # NEW — US1 (P1) — architectural test:
│                                            #                  scans `src/` for `import
│                                            #                  litellm` outside the
│                                            #                  LiteLLM adapter package per
│                                            #                  FR-005 + SC-002
├── test_020_canonical_error_mapping.py     # NEW — US1 (P1) — every LiteLLM exception
│                                            #                  class maps to a canonical
│                                            #                  `CanonicalError` per FR-008
├── test_020_stream_event_normalization.py  # NEW — US1 (P1) — Anthropic-style and OpenAI-
│                                            #                  style streams normalize into
│                                            #                  the single SACP `StreamEvent`
│                                            #                  shape per FR-009
├── test_020_mock_adapter_dispatch.py       # NEW — US2 (P2) — mock returns fixture-keyed
│                                            #                  responses; cost tracker
│                                            #                  records fixture token
│                                            #                  counts per SC-003
├── test_020_mock_adapter_fixture_missing.py # NEW — US2 (P2) — `MockFixtureMissing` on
│                                            #                  unconfigured input per
│                                            #                  FR-007 + SC-004
├── test_020_mock_adapter_no_network.py     # NEW — US2 (P2) — socket-level isolation;
│                                            #                  no outbound connection
│                                            #                  with mock adapter selected
├── test_020_mock_adapter_capabilities.py   # NEW — US2 (P2) — fixture-controllable
│                                            #                  `capabilities()` shape per
│                                            #                  spec acceptance scenario
├── test_020_capabilities_authority.py      # NEW — US1 (P1) — adapter `capabilities()`
│                                            #                  is authoritative; specs
│                                            #                  015/016/017/018 consume
│                                            #                  it (smoke contract)
└── fixtures/
    └── mock_adapter/                       # NEW — sample fixture sets per
                                             #       contracts/mock-fixtures.md
        ├── basic_responses.json
        ├── error_modes.json
        └── streaming_sequences.json
```

**Structure Decision**: Existing `src/api_bridge/` package is restructured into two subpackages (`litellm/` + `mock/`) plus the adapter ABC at the package root. The existing helper modules (`format.py`, `caching.py`, `tokenizer.py`, `model_limits.py`, `list_models.py`) stay where they are — they remain provider-neutral utilities the LiteLLM adapter consumes. The current `provider.py` (325 lines, the only `import litellm` site outside test code) is dissolved into `litellm/dispatch.py` + `litellm/errors.py` + `litellm/streaming.py` + `litellm/capabilities.py` for module-level cohesion. The MCP tools that consume `tokenizer.py` and `list_models.py` are unaffected — those imports remain stable.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(No violations.)

## Phase 0 — Outline & Research

Open decisions queued for `research.md`:

1. **`StreamEvent` shape**. FR-009 fixes the requirement (text deltas + tool-call deltas + finalization, single SACP event shape). Research finalizes the dataclass — at minimum `event_type` (enum: `text_delta`, `tool_call_delta`, `finalization`), `content` (str | None), `tool_call` (dict | None), `finish_reason` (str | None), `usage` (dict | None) on finalization. Decision criterion: shape MUST be implementable from both Anthropic-style and OpenAI-style streams without information loss; tool-call deltas MUST surface enough to reconstruct partial-then-complete tool calls.
2. **`CanonicalError` enumeration**. FR-008 fixes the seven categories (`error_5xx`, `error_4xx`, `auth_error`, `rate_limit`, `timeout`, `quality_failure`, `unknown`) matching spec 015 §FR-003. Research finalizes the dataclass shape — at minimum `category` (the seven-value enum), `retry_after_seconds` (int | None for `rate_limit`), `original_exception` (exc, retained for logging only — never raised back), `provider_message` (str | None for human-readable detail). The category-vs-detail split keeps the breaker's logic simple while preserving forensic detail in `routing_log`.
3. **`Capabilities` shape**. FR-011 fixes the field set (`supports_streaming`, `supports_tool_calling`, `supports_prompt_caching`, `max_context_tokens`, `tokenizer_name`, `recommended_temperature_range`). Research designs the lookup — does `capabilities(model)` cache per-model results in the adapter for the process lifetime, or recompute each call? Decision: cache (capabilities are model-static within a process; recomputing wastes negligible work but adds a virtual-method dispatch that fires often).
4. **Adapter registration mechanism**. FR-003 says "Adapter implementations register themselves in the registry at module import time." Research selects between two patterns: (a) decorator-based registration (`@AdapterRegistry.register("litellm")` on the class) — concise but couples implementation files to the registry import; (b) explicit registration in `src/api_bridge/__init__.py` (calling `register("litellm", LiteLLMAdapter)` at package-import time) — explicit but slightly more verbose. Decision criterion: minimize hidden state; explicit registration in `__init__.py` is preferred unless decorator-based is materially simpler.
5. **`get_adapter()` factory and process-scope singleton**. FR-002 says selection is process-wide and immutable for process lifetime. Research designs the singleton: read `SACP_PROVIDER_ADAPTER` once at startup, instantiate the adapter once, store in a module-level `_ACTIVE_ADAPTER` slot, and have `get_adapter()` return it on every call. Decision criterion: thread-safe initialization (FastAPI's startup hook is single-threaded; module-level slot suffices), no mid-process re-init API exposed (per FR-015).
6. **LiteLLM exception-to-canonical mapping table**. FR-008 says every LiteLLM exception class maps to a canonical category. Research enumerates LiteLLM's exception hierarchy (`AuthenticationError`, `BadRequestError`, `RateLimitError`, `Timeout`, `APIConnectionError`, `APIError`, `ContextWindowExceededError`, etc.) and assigns each to one of the seven canonical categories. Decision criterion: map by status code where available, by class name for connection/timeout errors. `ContextWindowExceededError` maps to `error_4xx` (not `quality_failure`) since it's a request-shape failure, not a generation-quality failure.
7. **Mock-adapter fixture format**. Spec §"Configuration (V16)" defers JSON-vs-YAML to the plan. Research recommends JSON: existing `tests/fixtures/` precedent uses JSON; the orchestrator's existing `json` standard-library import covers parsing without a new dep; YAML's `yaml` package would add a runtime dependency that violates "no new runtime dependencies" per Technical Context. Fixture file shape: top-level dict with two keys — `responses` (list of `{match: <input-pattern>, response: <fixture-response>}`) and `errors` (list of `{match: <input-pattern>, canonical_category: <enum-value>, retry_after_seconds: <int | null>}`).
8. **Fixture input matching**. Research designs the match-key shape — exact-match by message-list hash is brittle; substring-match on the last-message text is more useful for tests. Decision: hash-based match for byte-identical fixture replay, with substring fallback when no hash match. Both match modes are documented in `contracts/mock-fixtures.md`.
9. **Cross-validator dependency between the two new env vars**. `SACP_PROVIDER_ADAPTER=mock` makes `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` mandatory; `SACP_PROVIDER_ADAPTER=litellm` makes it ignored. Research designs the cross-validator pattern — mirrors spec 014's `SACP_AUTO_MODE_ENABLED` ↔ `SACP_DMA_DWELL_TIME_S` pair. Decision: implement as `validate_provider_adapter_mock_fixtures_path` that reads `SACP_PROVIDER_ADAPTER` first and applies its rules conditionally.
10. **Topology-7 forward note**. Spec §V12 marks topology 7 incompatible. Research drafts the controller-side gate analogous to specs 014/021 §V12: the adapter-init code checks `SACP_TOPOLOGY` env var and skips registry instantiation when it equals `7`. Same forward-document pattern.
11. **Spec 015 circuit-breaker integration point**. Spec FR-008 says the breaker consumes `adapter.normalize_error(exc)`. Research identifies the existing call sites in `src/orchestrator/circuit_breaker.py` that catch LiteLLM exception classes and designs the migration — replace `except litellm.RateLimitError` blocks with a generic `except Exception as exc` followed by `canonical = adapter.normalize_error(exc)` and dispatch on `canonical.category`. Decision criterion: minimize behavior change — every category that previously tripped the breaker MUST still trip it, with no expansion of the trip set.
12. **`provider_family` label sourcing for spec 016 metrics**. Spec FR-011 + cross-ref to spec 016 says `provider_family` Prometheus label values come from the adapter's `capabilities()` provider metadata. Research identifies the metadata field — adapter returns `provider_family` (string, bounded enum: `anthropic`, `openai`, `gemini`, `groq`, `ollama`, `vllm`, `unknown`) as part of `Capabilities`. Spec 016 consumes the field at metric-emit time. Decision: add `provider_family` to the `Capabilities` field set (not in spec FR-011's enumerated list, but research-time addition justified by cross-spec coupling); document in `contracts/adapter-interface.md`.

Output: [research.md](./research.md) with one decision section per open question.

## Phase 1 — Design & Contracts

**Prerequisites:** `research.md` complete.

1. **Data model** ([data-model.md](./data-model.md)) extracts entities from spec:
   - `ProviderAdapter` — abstract base class in `src/api_bridge/adapter.py`. Methods per FR-001: `dispatch(request)`, `dispatch_with_retry(request)`, `stream(request)`, `count_tokens(messages, model)`, `validate_credentials(api_key, model)`, `capabilities(model)`, `normalize_error(exc)`.
   - `AdapterRegistry` — process-scope singleton in `src/api_bridge/adapter.py`. Maps env-var values (`"litellm"`, `"mock"`, future names) to adapter classes. Read-only after orchestrator startup per FR-003.
   - `ProviderRequest` — frozen dataclass at the SACP <-> adapter boundary. Fields: `model`, `messages`, `api_key_encrypted`, `encryption_key`, `api_base`, `timeout`, `max_tokens`, `cache_directives`, `provider_specific` (opaque pass-through dict per spec assumption).
   - `ProviderResponse` — frozen dataclass at the SACP <-> adapter boundary. Existing type from `src/orchestrator/types.py`; relocates to `src/api_bridge/adapter.py` (canonical home). Fields preserve the pre-feature shape (FR-014 byte-identical regression): `model`, `content`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`. `provider_family` lives on `Capabilities` and is queried separately; `finish_reason` surfaces only on streaming `StreamEvent` finalizations.
   - `Capabilities` — frozen dataclass returned by `capabilities(model)`. Fields per FR-011 + research §3 + research §12: `supports_streaming` (bool), `supports_tool_calling` (bool), `supports_prompt_caching` (bool), `max_context_tokens` (int), `tokenizer_name` (str), `recommended_temperature_range` (tuple[float, float]), `provider_family` (str).
   - `CanonicalError` — frozen dataclass returned by `normalize_error(exc)`. Fields per research §2: `category` (enum, seven values), `retry_after_seconds` (int | None), `original_exception` (exc, log-only), `provider_message` (str | None).
   - `StreamEvent` — frozen dataclass per FR-009 + research §1. Fields: `event_type` (enum: text_delta, tool_call_delta, finalization), `content` (str | None), `tool_call` (dict | None), `finish_reason` (str | None on finalization), `usage` (dict | None on finalization).
   - `MockFixtureSet` (mock-only) — frozen dataclass loaded from `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` per research §7. Fields: `responses` (tuple of `(input_pattern, response_data)`), `errors` (tuple of `(input_pattern, canonical_category, retry_after_seconds)`).

2. **Contracts** ([contracts/](./contracts/)) — Phase 1 outputs five contract docs:
   - `contracts/env-vars.md` — two new vars with the six standard fields each (Default, Type, Valid range, Blast radius, Validation rule, Source spec). Cross-validator note for the `mock`-adapter dependency.
   - `contracts/adapter-interface.md` — `ProviderAdapter` ABC method signatures, lifecycle (instantiation at startup, immutable for process lifetime), registry semantics, the `provider_family` capability field.
   - `contracts/canonical-error-mapping.md` — table mapping every LiteLLM exception class to a `CanonicalError` category (seven enum values per FR-008 + spec 015 §FR-003). Cross-spec contract with spec 015's circuit breaker.
   - `contracts/stream-event-shape.md` — SACP `StreamEvent` dataclass fields per FR-009; documents how Anthropic-style and OpenAI-style provider streams normalize into this single shape (text deltas, tool-call deltas, finalization).
   - `contracts/mock-fixtures.md` — JSON fixture file format per research §7 + §8 (top-level `responses` + `errors` keys, hash-based and substring match modes, schema-validation rules).

3. **Quickstart** ([quickstart.md](./quickstart.md)) — operator workflow:
   - Verify default adapter (no env var → `litellm` selected; check startup banner).
   - Architectural-test verification (`pytest tests/test_020_no_litellm_imports.py` passes locally before merge).
   - Switch to mock adapter for testing (`SACP_PROVIDER_ADAPTER=mock`, `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH=path/to/fixtures.json`, restart, observe deterministic responses).
   - Add a new adapter (registry registration in `src/api_bridge/<name>/__init__.py`; FR-005 architectural test continues to pass; future spec governs the new adapter's behavior).
   - Disable / rollback (unset env vars, restart — defaults restore the LiteLLM adapter).
   - Diagnostic: capture canonical-error mappings from `routing_log` to verify spec 015 breaker integration.

4. **Agent context update**: run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType claude` to merge tech into `CLAUDE.md`.

5. **Re-evaluate Constitution Check** post-design — confirm no V14/V15/V16/V17 surfaces shifted from the pre-design table above. Phase 1 design preserves the V16 deliverable gate (FR-013) and adds no new fail-closed surfaces beyond those already enumerated.

### Post-design re-evaluation (2026-05-08)

Re-checked all V1-V19 rows from the Constitution Check table against the Phase 1 deliverables (data-model.md, contracts/*.md, quickstart.md, updated CLAUDE.md):

- **No surfaces shifted.** Every gate that PASSed pre-design still PASSes; the V16 PASS-ON-DELIVERY gate remains the only conditional row, contingent on the validators + `docs/env-vars.md` sections landing before `/speckit.tasks`.
- **No new fail-closed surfaces** introduced beyond the two enumerated in the V15 row (invalid env var → exit, `MockFixtureMissing` → raise rather than default, adapter-init failure → exit).
- **No new transcript-mutation paths** introduced (V17 unchanged); the adapter operates pre-bridge per §4.12 and never writes to the canonical transcript.
- **No new derived artifacts** introduced (V18 unchanged); `StreamEvent`, `CanonicalError`, and `Capabilities` are translation primitives, not derivations of transcript content.
- **Cross-spec contracts** (15/16/17/18) preserve the FR-008 / FR-011 / FR-012 surfaces named in the spec; data-model.md's "Cross-spec integration points" section captures the consumed surfaces explicitly for /speckit.tasks.

No Complexity Tracking entries needed.

**Output**: data-model.md, contracts/*.md, quickstart.md, updated CLAUDE.md.

## Notes for `/speckit.tasks`

- **V16 deliverable gate (FR-013)**: tasks MUST gate validator + doc work BEFORE any code-path work. The two new env vars (`SACP_PROVIDER_ADAPTER`, `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`) need validator functions in `src/config/validators.py` registered in the `VALIDATORS` tuple, plus full sections in `docs/env-vars.md` with the six standard fields each. CI gate `scripts/check_env_vars.py` enforces drift detection; landing the validators + docs first keeps the regression test (SC-001) executable from the start.
- **Cross-validator dependency**: `SACP_PROVIDER_ADAPTER=mock` makes `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` mandatory; `=litellm` makes it ignored. The validator implementation mirrors spec 014's `SACP_AUTO_MODE_ENABLED` ↔ `SACP_DMA_DWELL_TIME_S` precedent. Tasks should land both validators together so the cross-check works at first commit.
- **Single-PR cutover (clarification 2026-05-08)**: every consumer of `from src.api_bridge.provider` migrates to `from src.api_bridge.adapter import get_adapter` in one PR. No parallel-old-and-new path window. The existing `src/api_bridge/provider.py` is deleted; its body lives in `src/api_bridge/litellm/dispatch.py`. Tasks MUST land the adapter ABC + `LiteLLMAdapter` + every consumer migration in a single mergeable unit.
- **Architectural test (FR-005) lands first as a canary**. `tests/test_020_no_litellm_imports.py` scans `src/` for `import litellm` / `from litellm` outside `src/api_bridge/litellm/`. The test SHOULD initially fail (proving it's wired correctly) and pass only after every consumer migration is complete. Land the test BEFORE the migration tasks so the migration's completion is mechanically verifiable.
- **Regression contract (SC-001)**: pre-feature acceptance suite passes byte-identically with `SACP_PROVIDER_ADAPTER=litellm` (default). Land the regression-test wiring early as a canary for the byte-identical guarantee; any drift surfaces immediately.
- **Spec 015 circuit-breaker integration (FR-008)**: the breaker swaps from catching LiteLLM exception classes to consuming `adapter.normalize_error(exc)`. This is the deepest cross-spec coupling — tasks here ship the adapter-side `normalize_error` AND the breaker-side migration in the same PR per the single-PR cutover discipline.
- **Spec 016 metrics integration (FR-011 + research §12)**: `provider_family` Prometheus label sources from `adapter.capabilities(model).provider_family`. Tasks here ship the field on `Capabilities`; spec 016's tasks consume it. No spec-016 task lands here.
- **Spec 018 deferred-loading integration (FR-012)**: `count_tokens()` becomes the budget primitive. Tasks here ship the adapter method; spec 018's tasks consume it. No spec-018 task lands here.
- **Topology-7 forward note**: adapter-init checks `SACP_TOPOLOGY` and skips registration when topology 7 is active. Same forward-document pattern as specs 014/021 — tasks land the gate, no topology-7-specific behavior implemented.
- **Mock-adapter fixture format (research §7)**: JSON, not YAML. No new runtime dependency; the existing `json` stdlib import suffices. Fixture files live under `tests/fixtures/mock_adapter/` per the established test-fixture pattern.
- **No DB schema changes**: this is internal-architecture refactor only. No alembic migration. No `tests/conftest.py` schema-mirror update required (memory: "Test conftest schema mirrors alembic" applies only when migrations land — non-applicable here).
- **Phase 1-back-fill framing (spec assumption)**: per the Phase 3 declaration recorded 2026-05-05, the spec ships as Phase-3 scaffolding completing a Phase-1 architectural gap that earlier specs accreted around. Same back-fill pattern as specs 015/016/017/018/019. No additional dependency on those specs' implementation status; spec 020's adapter abstraction is the substrate they consume.
