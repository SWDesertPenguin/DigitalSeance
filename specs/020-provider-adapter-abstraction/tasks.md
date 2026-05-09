---

description: "Task list for implementing spec 020 (pluggable provider adapter abstraction)"
---

# Tasks: Pluggable Provider Adapter Abstraction

**Input**: Design documents from `/specs/020-provider-adapter-abstraction/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — spec defines three Independent Tests + 12 Acceptance Scenarios across US1-US3, and plan.md enumerates test files per story. Spec 015 circuit-breaker test migration to canonical categories lands in the same single-PR cutover per FR-005's architectural-test discipline.

**Organization**: Tasks grouped by user story so each can be implemented and tested independently. Phase 2 covers shared infrastructure (V16 deliverable gate per spec FR-013, ABC + canonical types + registry, the FR-005 architectural-test canary, and the SC-001 regression canary). Per the resolved clarification 2026-05-08 ("single-PR cutover"), every consumer migration of `from src.api_bridge.provider import dispatch_with_retry` to `get_adapter().dispatch_with_retry(...)` lands in this same task set; FR-005's architectural test gates the cutover's completion.

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, OR independent functions in the same file with no shared edit point)
- **[Story]**: US1 / US2 / US3 (no label for Setup, Foundational, Polish)

## Path Conventions

Single project, paths under repo root. Backend code under [src/](src/); tests under [tests/](tests/) per [plan.md "Source Code"](./plan.md). The adapter abstraction restructures the existing [src/api_bridge/](src/api_bridge/) package; no new top-level packages.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm baseline + create empty package skeletons for the LiteLLM and mock adapter subpackages.

- [X] T001 Verify on branch `020-provider-adapter-abstraction` and run `python -m src.run_apps --validate-config-only` to confirm V16 baseline passes before any new validators land
- [X] T002 [P] Create empty package skeleton at [src/api_bridge/litellm/__init__.py](src/api_bridge/litellm/__init__.py) (module docstring referencing spec 020 + a `# AdapterRegistry.register call lands in T030` comment)
- [X] T003 [P] Create empty package skeleton at [src/api_bridge/mock/__init__.py](src/api_bridge/mock/__init__.py) (module docstring + `# AdapterRegistry.register call lands in T054` comment)
- [X] T004 [P] Create empty fixture directory and three sample files at [tests/fixtures/mock_adapter/basic_responses.json](tests/fixtures/mock_adapter/basic_responses.json), [tests/fixtures/mock_adapter/error_modes.json](tests/fixtures/mock_adapter/error_modes.json), [tests/fixtures/mock_adapter/streaming_sequences.json](tests/fixtures/mock_adapter/streaming_sequences.json) (each containing `{"responses": [], "errors": [], "capabilities": {"default": {...}}}` minimum-viable shape per [contracts/mock-fixtures.md](./contracts/mock-fixtures.md))

---

## Phase 2: Foundational (Blocking Prerequisites — V16 Gate per FR-013 + Adapter ABC + Canary Tests)

**Purpose**: V16 env-var deliverables (2 validators + 2 docs sections), `ProviderAdapter` ABC + canonical types + registry, the FR-005 architectural-test canary, and the SC-001 regression canary. All three user stories depend on these.

**⚠️ CRITICAL**: No user-story task in Phase 3+ may begin until Phase 2 completes. The V16 gate is non-negotiable per spec FR-013, and the architectural-test canary must be wired (and initially failing) before consumer migration begins.

### V16 deliverable gate (2 validators + 2 doc sections)

- [X] T005 [P] Add `validate_provider_adapter` to [src/config/validators.py](src/config/validators.py) per [contracts/env-vars.md §SACP_PROVIDER_ADAPTER](./contracts/env-vars.md): hardcoded `valid = {"litellm", "mock"}`; default `"litellm"`; out-of-set exits at startup with error message listing registered names
- [X] T006 [P] Add `validate_provider_adapter_mock_fixtures_path` to [src/config/validators.py](src/config/validators.py) per [contracts/env-vars.md §SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH](./contracts/env-vars.md): cross-validator dependency reads `SACP_PROVIDER_ADAPTER` first; required + readable + JSON-parseable when adapter is `"mock"`; ignored otherwise
- [X] T007 Append `validate_provider_adapter` and `validate_provider_adapter_mock_fixtures_path` to the `VALIDATORS` tuple at the bottom of [src/config/validators.py](src/config/validators.py) in that order so the adapter-name check fires before the fixtures-path check (depends on T005, T006)
- [X] T008 [P] Add `### SACP_PROVIDER_ADAPTER` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields per [contracts/env-vars.md](./contracts/env-vars.md)
- [X] T009 [P] Add `### SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` section to [docs/env-vars.md](docs/env-vars.md) with the six standard fields, including the cross-validator dependency note
- [X] T010 Run `python scripts/check_env_vars.py` from repo root and confirm V16 CI gate green for the two new vars (validators + doc sections in lockstep)
- [X] T011 [P] Validator unit tests in [tests/test_020_validators.py](tests/test_020_validators.py): each of the two validators — valid value passes, out-of-range raises `ConfigValidationError` naming the offending var, mock-without-fixtures raises with the documented error message, fixtures-path-not-a-file raises, fixtures-path-with-bad-json raises

### `ProviderAdapter` ABC + canonical types + registry

- [X] T012 Implement `CanonicalErrorCategory` enum + `CanonicalError` frozen dataclass in [src/api_bridge/adapter.py](src/api_bridge/adapter.py) per [data-model.md §CanonicalError](./data-model.md) and [research.md §2](./research.md) — seven enum values matching spec 015 §FR-003
- [X] T013 [P] Implement `StreamEventType` enum + `StreamEvent` frozen dataclass in [src/api_bridge/adapter.py](src/api_bridge/adapter.py) per [data-model.md §StreamEvent](./data-model.md) and [research.md §1](./research.md) — three event types
- [X] T014 [P] Implement `Capabilities` frozen dataclass in [src/api_bridge/adapter.py](src/api_bridge/adapter.py) per [data-model.md §Capabilities](./data-model.md) and [research.md §3](./research.md) — seven fields including `provider_family`
- [X] T015 [P] Implement `ProviderRequest` frozen dataclass in [src/api_bridge/adapter.py](src/api_bridge/adapter.py) per [data-model.md §ProviderRequest](./data-model.md) — nine fields including `provider_specific` opaque pass-through
- [X] T016 Relocate `ProviderResponse` from [src/orchestrator/types.py](src/orchestrator/types.py) to [src/api_bridge/adapter.py](src/api_bridge/adapter.py); add re-export shim in [src/orchestrator/types.py](src/orchestrator/types.py) so existing imports continue to work (depends on T012-T015)
- [X] T017 [US1] Implement `ProviderAdapter` ABC in [src/api_bridge/adapter.py](src/api_bridge/adapter.py) per [contracts/adapter-interface.md](./contracts/adapter-interface.md) — seven abstract methods with full type signatures (no actual story label needed; this is foundational, but flagged for clarity that the ABC governs all stories)
- [X] T018 Implement `AdapterRegistry` class with `register` / `get` / `names` classmethods in [src/api_bridge/adapter.py](src/api_bridge/adapter.py) per [contracts/adapter-interface.md "Registry semantics"](./contracts/adapter-interface.md) and [research.md §4](./research.md); duplicate-registration raises ValueError
- [X] T019 Implement `_ACTIVE_ADAPTER` slot + `initialize_adapter()` + `get_adapter()` in [src/api_bridge/adapter.py](src/api_bridge/adapter.py) per [research.md §5](./research.md) — startup-only init; SystemExit on invalid name; double-init guard; topology-7 early-return per [research.md §10](./research.md)
- [X] T020 [P] Unit tests for ABC + registry + factory in [tests/test_020_adapter_registry.py](tests/test_020_adapter_registry.py): registry register/get/names; duplicate-registration raises; `get_adapter()` before init raises; `initialize_adapter()` twice raises; SystemExit on invalid `SACP_PROVIDER_ADAPTER` value with message listing registered names per SC-005

### FR-005 architectural-test canary

- [X] T021 Implement architectural test in [tests/test_020_no_litellm_imports.py](tests/test_020_no_litellm_imports.py) that walks [src/](src/) and asserts no `import litellm` / `from litellm` statements exist outside `src/api_bridge/litellm/`. Test SHOULD initially fail (the existing `src/api_bridge/provider.py` violates) — failure proves the test is wired correctly. Test transitions to passing only after T040+ complete.

### SC-001 regression canary

- [X] T022 [P] Set up CI matrix entry that runs the full pre-feature acceptance suite with `SACP_PROVIDER_ADAPTER=litellm` (default) per SC-001 — verifies byte-identical regression behavior across migration. Add to [.github/workflows/](.github/workflows/) test job or equivalent CI config; document the matrix entry in [contracts/adapter-interface.md "Migration contract"](./contracts/adapter-interface.md) reference.

**Checkpoint**: V16 gate green; ABC + canonical types + registry available; architectural-test canary wired (failing); SC-001 regression canary running on CI. User-story phases unblocked. Cutover discipline begins in US1.

---

## Phase 3: User Story 1 — LiteLLM-backed adapter ships behind the interface with byte-identical behavior (Priority: P1) 🎯 MVP

**Goal**: The dispatch path no longer imports `litellm` directly. Every call previously reading a LiteLLM-native field, raising a LiteLLM exception, or consuming a LiteLLM streaming event now goes through the `ProviderAdapter` interface. `SACP_PROVIDER_ADAPTER=litellm` (default) selects `LiteLLMAdapter`, which translates between SACP's internal message format and LiteLLM's API. Byte-identical regression behavior preserved per FR-014 + SC-001.

**Independent Test**: Run the full pre-feature acceptance suite with `SACP_PROVIDER_ADAPTER=litellm` (default). Verify every test passes byte-identically — same response content, same audit entries, same metric values, same per-turn timing, same cost-tracker deltas. Separately, verify the FR-005 architectural test passes (no `import litellm` outside `src/api_bridge/litellm/`).

### Tests for User Story 1

- [X] T023 [P] [US1] Acceptance scenario 1 (regression suite passes byte-identically with default `SACP_PROVIDER_ADAPTER=litellm`) — covered by T022's CI matrix entry; document the assertion in [tests/test_020_litellm_adapter_regression.py](tests/test_020_litellm_adapter_regression.py) as a smoke test that imports `get_adapter()` and confirms `type(adapter).__name__ == "LiteLLMAdapter"`
- [X] T024 [P] [US1] Acceptance scenario 2 (architectural test passes after migration) — already wired in T021; this task is to flip T021's expected status to PASS once consumer migrations land
- [X] T025 [P] [US1] Acceptance scenario 3 (Anthropic-style and OpenAI-style streams normalize to single SACP `StreamEvent` shape) in [tests/test_020_stream_event_normalization.py](tests/test_020_stream_event_normalization.py) per [contracts/stream-event-shape.md](./contracts/stream-event-shape.md): mock provider streams of each shape, assert SACP event sequences match the contract
- [X] T026 [P] [US1] Acceptance scenario 4 (`adapter.normalize_error(exc)` returns canonical category matching spec 015 §FR-003 enumeration) in [tests/test_020_canonical_error_mapping.py](tests/test_020_canonical_error_mapping.py) per [contracts/canonical-error-mapping.md "Test contract"](./contracts/canonical-error-mapping.md): one assertion per row of the 14-row mapping table
- [X] T027 [P] [US1] `capabilities()` authority smoke test in [tests/test_020_capabilities_authority.py](tests/test_020_capabilities_authority.py): assert per-process per-model cache works (call twice, second call returns the same instance); assert all seven `Capabilities` fields are populated for representative models from each provider family

### Implementation for User Story 1 — `LiteLLMAdapter` package

- [X] T028 [P] [US1] Move dispatch logic from [src/api_bridge/provider.py](src/api_bridge/provider.py) to [src/api_bridge/litellm/dispatch.py](src/api_bridge/litellm/dispatch.py) — current `dispatch`, `dispatch_with_retry`, `_call_litellm`, `_decrypt_key`, `_extract_response`, `_log_heartbeat` helpers; `import litellm` lives only here
- [X] T029 [P] [US1] Implement `_normalize_litellm_error(exc)` in [src/api_bridge/litellm/errors.py](src/api_bridge/litellm/errors.py) per [contracts/canonical-error-mapping.md "Implementation skeleton"](./contracts/canonical-error-mapping.md) — 14-row mapping table; UNKNOWN fallback for unmapped exceptions
- [X] T030 [P] [US1] Implement `_normalize_litellm_stream(provider_iter)` async generator in [src/api_bridge/litellm/streaming.py](src/api_bridge/litellm/streaming.py) per [contracts/stream-event-shape.md "Anthropic" + "OpenAI"](./contracts/stream-event-shape.md): converts LiteLLM-emitted stream chunks into `StreamEvent` objects; handles Anthropic `content_block_delta` + `message_delta` + `message_stop` and OpenAI `delta.content` + `delta.tool_calls` + `finish_reason`
- [X] T031 [P] [US1] Implement `_compute_capabilities(model)` in [src/api_bridge/litellm/capabilities.py](src/api_bridge/litellm/capabilities.py) per [research.md §3 + §12](./research.md): consults `litellm.get_llm_provider(model)` + [src/api_bridge/model_limits.py](src/api_bridge/model_limits.py); applies the `_PROVIDER_FAMILY_MAP` from [research.md §12](./research.md) to produce the bounded `provider_family` enum value. Note: `model_limits.py`'s `_from_litellm()` helper (currently does an inline `import litellm` per [src/api_bridge/model_limits.py:62-69](src/api_bridge/model_limits.py)) MUST relocate INTO `src/api_bridge/litellm/capabilities.py` (or a sibling file under the LiteLLM package) so FR-005's architectural test passes; `model_limits.py` keeps only its provider-neutral fallback table.
- [X] T032 [P] [US1] Implement `_count_tokens(messages, model)` in [src/api_bridge/litellm/tokens.py](src/api_bridge/litellm/tokens.py): re-uses [src/api_bridge/tokenizer.py](src/api_bridge/tokenizer.py); conservative-overestimate fallback path for unknown tokenizer with audit-entry emit per FR-012
- [X] T033 [US1] Implement `LiteLLMAdapter` class in [src/api_bridge/litellm/adapter.py](src/api_bridge/litellm/adapter.py) per [contracts/adapter-interface.md](./contracts/adapter-interface.md) — extends `ProviderAdapter`; methods delegate to T028-T032 modules; per-process per-model `_cap_cache` dict (depends on T028-T032)
- [X] T034 [US1] Wire `AdapterRegistry.register("litellm", LiteLLMAdapter)` call in [src/api_bridge/litellm/__init__.py](src/api_bridge/litellm/__init__.py) per [research.md §4](./research.md) (depends on T033)

### Single-PR cutover — consumer migration (FR-005 architectural-test gates completion)

- [X] T035 [US1] Replace `from src.api_bridge.provider import dispatch_with_retry` in BOTH [src/orchestrator/loop.py](src/orchestrator/loop.py) AND [src/orchestrator/summarizer.py](src/orchestrator/summarizer.py) with `from src.api_bridge.adapter import get_adapter`; replace each direct `dispatch_with_retry(...)` call (loop.py line 975, summarizer.py line 229 per pre-feature grep) with `await get_adapter().dispatch_with_retry(ProviderRequest(...))`; preserve all existing call-site argument passing (depends on T034)
- [X] T036 [US1] Migrate the LiteLLM exception-class catches that currently live INSIDE [src/api_bridge/provider.py](src/api_bridge/provider.py) (lines 125 + 127 — `litellm.ContextWindowExceededError`, `litellm.RateLimitError`) to the new home in [src/api_bridge/litellm/dispatch.py](src/api_bridge/litellm/dispatch.py) and [src/api_bridge/litellm/errors.py](src/api_bridge/litellm/errors.py) per T028 + T029. The orchestrator-side breaker integration in [src/orchestrator/loop.py](src/orchestrator/loop.py) (`_record_failure_and_announce` call sites lines 763/938/942 — see pre-feature grep) consumes the `CanonicalError.category` returned from `adapter.normalize_error(exc)` rather than catching LiteLLM exception classes directly. Note: [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py) itself does not catch provider exceptions — it only records `participant_id` failures via `record_failure()`; the canonical-category consumption point is the loop-level handler that calls into the breaker (depends on T034)
- [X] T037 [US1] Hook `initialize_adapter()` into the FastAPI `lifespan` async context manager in [src/mcp_server/app.py](src/mcp_server/app.py) (the `_lifespan` asynccontextmanager around line 32); call AFTER `validate_all()` runs in the existing startup path and BEFORE the FastAPI router accepts connections; ensure both `import src.api_bridge.litellm` and `import src.api_bridge.mock` execute before init reads the env var so `AdapterRegistry` has both names registered (depends on T034)
- [X] T038 [US1] Replace any remaining `import litellm` / `from litellm` site under [src/](src/) with adapter-mediated calls — search via `grep -rn "import litellm\|from litellm" src/` and migrate each site one by one. Sites to expect (verified via pre-feature grep): [src/api_bridge/provider.py:11](src/api_bridge/provider.py) (deleted via T039), [src/api_bridge/model_limits.py:65](src/api_bridge/model_limits.py) inline import inside `_from_litellm()` (relocated INTO the LiteLLM adapter package per T031's note). After this task, the only files under `src/` containing `litellm` MUST be inside `src/api_bridge/litellm/`
- [X] T039 [US1] Delete [src/api_bridge/provider.py](src/api_bridge/provider.py) (its body relocated to [src/api_bridge/litellm/dispatch.py](src/api_bridge/litellm/dispatch.py) per T028); update [src/api_bridge/__init__.py](src/api_bridge/__init__.py) to re-export `get_adapter` and the canonical types from [src/api_bridge/adapter.py](src/api_bridge/adapter.py) (depends on T028, T035-T038)
- [X] T040 [US1] Audit dispatch-level tests that currently reference LiteLLM exception classes for stub side-effects ([tests/test_dispatch.py](tests/test_dispatch.py), [tests/test_loop_integration.py](tests/test_loop_integration.py), [tests/test_provider_compat_matrix.py](tests/test_provider_compat_matrix.py), [tests/integration/test_pipeline_through_loop.py](tests/integration/test_pipeline_through_loop.py), [tests/integration/test_caching_e2e.py](tests/integration/test_caching_e2e.py)) — most are LiteLLM adapter unit tests by nature and STAY (litellm imports inside `tests/` are permitted per FR-005 which constrains `src/` only). Tests that exercise the breaker via canonical categories ([tests/test_circuit_breaker.py](tests/test_circuit_breaker.py) — currently does not import litellm) gain a sibling `tests/test_020_breaker_canonical_dispatch.py` that drives the breaker from the loop-level integration through `adapter.normalize_error(exc)` to confirm canonical-category dispatch matches pre-feature behavior (depends on T036)
- [X] T041 [US1] Run [tests/test_020_no_litellm_imports.py](tests/test_020_no_litellm_imports.py) (T021's canary) and confirm it now passes — proves T035-T038 cutover is complete (depends on T035-T040)
- [X] T042 [US1] Run the full pre-feature acceptance suite with `SACP_PROVIDER_ADAPTER=litellm` (default) and confirm byte-identical regression per SC-001; if any test fails, the regression is a defect — investigate the LiteLLM adapter's translation logic (depends on T035-T041)

### Startup banner (operator-facing)

- [X] T043 [P] [US1] Emit startup banner line `[startup] Provider adapter: <name> (<details>)` from `initialize_adapter()` in [src/api_bridge/adapter.py](src/api_bridge/adapter.py) per [quickstart.md §1](./quickstart.md) — operators see which adapter is active; use existing structured-logging path (no `print` statements)

**Checkpoint**: LiteLLM adapter ships behind the interface; FR-005 architectural test passes; SC-001 byte-identical regression confirmed in CI; spec 015 breaker integration migrated. US1 fully functional. The interface IS the swap path — the v1 deliverable.

---

## Phase 4: User Story 2 — Mock adapter enables deterministic testing without network or provider keys (Priority: P2)

**Goal**: Tests that need specific response content, token counts, streaming-event sequences, or error modes drop network and provider keys. `SACP_PROVIDER_ADAPTER=mock` selects `MockAdapter`; fixture file at `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` keys responses on input shape; `MockFixtureMissing` raises rather than silently returning a default per FR-007.

**Independent Test**: Set `SACP_PROVIDER_ADAPTER=mock` and `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` to a fixture file. Run a session whose participant config selects a fixture set. Verify mock dispatches return configured response content + token counts; streaming events emerge in configured order; no outbound network call (verified by socket-level isolation harness).

### Tests for User Story 2

- [X] T044 [P] [US2] Acceptance scenario 1 (fixture configured to return `("hello world", 42, 10)` produces matching `ProviderResponse` and matching cost-tracker + spec 016 metric increments) in [tests/test_020_mock_adapter_dispatch.py](tests/test_020_mock_adapter_dispatch.py)
- [X] T045 [P] [US2] Acceptance scenario 2 (fixture configured to raise 5xx → `normalize_error()` returns `error_5xx` → spec 015 breaker trips after threshold) in [tests/test_020_mock_adapter_dispatch.py](tests/test_020_mock_adapter_dispatch.py)
- [X] T046 [P] [US2] Acceptance scenario 3 (no outbound network call when mock selected) in [tests/test_020_mock_adapter_no_network.py](tests/test_020_mock_adapter_no_network.py) — use a socket-level isolation harness (e.g., monkey-patch `socket.create_connection` to raise) to assert mock-adapter dispatch makes no outbound connection
- [X] T047 [P] [US2] Acceptance scenario 4 (fixture-controllable `capabilities()` shape — tests can simulate "no tool calling" or "200K-context" model) in [tests/test_020_mock_adapter_capabilities.py](tests/test_020_mock_adapter_capabilities.py)
- [X] T048 [P] [US2] `MockFixtureMissing` exception test in [tests/test_020_mock_adapter_fixture_missing.py](tests/test_020_mock_adapter_fixture_missing.py) per FR-007 + SC-004: drive an unconfigured input; assert exception is raised (not a default response); assert exception payload names the missing fixture key (canonical hash + last-message substring)

### Implementation for User Story 2 — `MockAdapter` package

- [X] T049 [P] [US2] Implement `MockFixtureSet` frozen dataclass + `_load(path)` JSON loader in [src/api_bridge/mock/fixtures.py](src/api_bridge/mock/fixtures.py) per [contracts/mock-fixtures.md](./contracts/mock-fixtures.md) and [data-model.md §MockFixtureSet](./data-model.md): top-level `responses` + `errors` + `capabilities` keys; schema validation raises `MockFixtureSchemaError` on shape failure
- [X] T050 [P] [US2] Implement `_match_fixture(messages, fixtures)` in [src/api_bridge/mock/fixtures.py](src/api_bridge/mock/fixtures.py) per [research.md §8](./research.md): hash-mode tried first, substring fallback; canonical hash is `sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False))`
- [X] T051 [P] [US2] Implement `MockFixtureMissing`, `MockInjectedError`, `MockStreamingError`, `MockFixtureSchemaError` exception classes in [src/api_bridge/mock/errors.py](src/api_bridge/mock/errors.py) per [contracts/mock-fixtures.md](./contracts/mock-fixtures.md) and [contracts/stream-event-shape.md "Error handling during streaming"](./contracts/stream-event-shape.md)
- [X] T052 [P] [US2] Implement `_default_stream(response)` and `_explicit_stream(events)` helpers in [src/api_bridge/mock/streaming.py](src/api_bridge/mock/streaming.py) per [contracts/stream-event-shape.md "Mock adapter"](./contracts/stream-event-shape.md): default is single `TEXT_DELTA` + `FINALIZATION`; explicit consumes the fixture's `stream_events` list
- [X] T053 [US2] Implement `MockAdapter` class in [src/api_bridge/mock/adapter.py](src/api_bridge/mock/adapter.py) per [contracts/adapter-interface.md](./contracts/adapter-interface.md): extends `ProviderAdapter`; loads fixtures from `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` at `__init__`; `dispatch_with_retry` matches fixture and returns `ProviderResponse` or raises `MockInjectedError`; `stream` yields fixture-driven `StreamEvent`s; `normalize_error` maps `MockInjectedError` → configured `CanonicalErrorCategory` and falls through to UNKNOWN for unexpected exceptions; `capabilities` reads from fixture's `capabilities` dict (default key `"default"`); `count_tokens` returns a deterministic count based on message-text length (test-controllable) (depends on T049-T052)
- [X] T054 [US2] Wire `AdapterRegistry.register("mock", MockAdapter)` call in [src/api_bridge/mock/__init__.py](src/api_bridge/mock/__init__.py) per [research.md §4](./research.md) (depends on T053)

### Sample fixture content

- [X] T055 [P] [US2] Populate [tests/fixtures/mock_adapter/basic_responses.json](tests/fixtures/mock_adapter/basic_responses.json) with at least one hash-mode and one substring-mode `responses` entry per [contracts/mock-fixtures.md](./contracts/mock-fixtures.md); used by T044
- [X] T056 [P] [US2] Populate [tests/fixtures/mock_adapter/error_modes.json](tests/fixtures/mock_adapter/error_modes.json) with one `errors` entry per `CanonicalErrorCategory` (seven entries); used by T045 + spec 015 breaker tests
- [X] T057 [P] [US2] Populate [tests/fixtures/mock_adapter/streaming_sequences.json](tests/fixtures/mock_adapter/streaming_sequences.json) with at least one explicit `stream_events` list demonstrating the contract from [contracts/stream-event-shape.md](./contracts/stream-event-shape.md)
- [X] T058 [P] [US2] Implement helper script [scripts/compute_mock_fixture_hash.py](scripts/compute_mock_fixture_hash.py) per [contracts/mock-fixtures.md "Fixture maintenance"](./contracts/mock-fixtures.md): reads message-list JSON from stdin, prints canonical sha256 hex; runnable by test authors to populate hash-mode fixtures

**Checkpoint**: Mock adapter ships with deterministic dispatch, injectable error modes, fixture-controllable capabilities, and the documented `MockFixtureMissing` semantics. Spec 015 breaker tests can now run against `SACP_PROVIDER_ADAPTER=mock` per SC-003.

---

## Phase 5: User Story 3 — Future provider-specific adapters slot in behind a feature flag without touching dispatch (Priority: P3)

**Goal**: Confirm the adapter interface is genuinely abstraction-shaped (not LiteLLM-shaped) by verifying both adapters coexist in the same process at registration time, the interface is implementable by two unrelated adapters without dispatch-path changes, and an invalid `SACP_PROVIDER_ADAPTER` value fails-closed at startup.

**Independent Test**: Confirm the interface is implementable by two unrelated adapters (LiteLLM + mock) without dispatch-path changes. Confirm `SACP_PROVIDER_ADAPTER=mock` selects the mock and `=litellm` selects LiteLLM. Confirm an invalid value fails-closed at startup with a clear error listing all registered adapter names.

### Tests for User Story 3

- [X] T059 [P] [US3] Acceptance scenario 1 (interface implementable by both adapters without dispatch-path file change) — covered by T021 architectural test (no `import litellm` outside the adapter package); add a parallel architectural assertion in [tests/test_020_adapter_registry.py](tests/test_020_adapter_registry.py) that walks dispatch-path files (e.g., [src/orchestrator/loop.py](src/orchestrator/loop.py), [src/orchestrator/circuit_breaker.py](src/orchestrator/circuit_breaker.py)) and asserts no `import` statement names a specific adapter package (only `from src.api_bridge.adapter import ...`)
- [X] T060 [P] [US3] Acceptance scenario 2 (invalid `SACP_PROVIDER_ADAPTER` fails-closed at startup with error listing registered names) in [tests/test_020_adapter_registry.py](tests/test_020_adapter_registry.py) per SC-005 — already partially covered by T020; this task adds the SC-005 specific exit-message assertion
- [X] T061 [P] [US3] Acceptance scenario 3 (future adapter via registry registration loads cleanly) in [tests/test_020_adapter_registry.py](tests/test_020_adapter_registry.py): construct a fake `class FutureAdapter(ProviderAdapter): ...` minimal subclass; register under name `"future_test"`; assert `initialize_adapter()` with `SACP_PROVIDER_ADAPTER=future_test` produces a `FutureAdapter` instance via the registry; cleanup the registration in test teardown
- [X] T062 [P] [US3] Acceptance scenario 4 (LiteLLM and mock coexist without dependency conflicts; only env-var-selected adapter is instantiated) in [tests/test_020_adapter_registry.py](tests/test_020_adapter_registry.py): import both packages; verify both classes registered; instantiate one and confirm the other class object exists in the registry but is not constructed

### Implementation for User Story 3 — Forward-compatibility verification

US3 has no new implementation tasks beyond what US1+US2 already produced — the verification is contractual, not behavioral. The single architectural assertion added in T059 is the concrete deliverable.

- [X] T063 [P] [US3] Documentation pass: confirm [quickstart.md §4 "Add a future provider-specific adapter"](./quickstart.md) lists the four mechanical steps (create package, amend validator, import at startup, ship); verify the steps match what T034 + T054 actually do for the v1 LiteLLM and mock adapters

**Checkpoint**: Forward-compatibility verified. The adapter interface is genuinely abstraction-shaped; future provider-specific adapters can land as their own specs without touching the dispatch path.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification, performance characterization, documentation cleanup, and cross-spec integration confirmation.

- [ ] T064 [P] Run [quickstart.md §1 "Verify the default LiteLLM adapter is active"](./quickstart.md) end-to-end against a live container; confirm startup banner matches; confirm regression suite passes
- [ ] T065 [P] Run [quickstart.md §3 "Switch to the mock adapter for testing"](./quickstart.md) end-to-end; confirm mock adapter selected, fixtures loaded, no outbound network (use `tcpdump` or equivalent)
- [ ] T066 [P] Run [quickstart.md §5 "Diagnose dispatch behavior"](./quickstart.md) SQL queries against staging routing_log to confirm `adapter_name`, `original_exception_class`, `normalize_error_category`, `retry_after_seconds`, and `provider_family` columns populate correctly
- [ ] T067 [P] V14 budget verification per [quickstart.md §7 "Performance characterization"](./quickstart.md): query `routing_log` for `dispatch_duration_ms` percentiles with the LiteLLM adapter; compare to pre-feature historical baselines; confirm delta fits within V14 per-stage budget tolerance
- [ ] T068 [P] V14 budget 2 verification: query `security_events` for `normalize_error_duration_us` percentiles; confirm constant-time `O(1)` (single-digit microseconds at p99)
- [ ] T069 [P] Cross-spec integration smoke test for spec 016 metrics: query Prometheus for `sacp_provider_dispatch_total{provider_family=~"anthropic|openai|gemini|groq|ollama|vllm|mock"}` and confirm only the bounded enum values appear
- [ ] T070 [P] Cross-spec integration smoke test for spec 017 freshness: trigger a tool-list change with a model whose `capabilities().supports_prompt_caching=true`; confirm prompt-cache invalidation logic fires (consumes `Capabilities.supports_prompt_caching`)
- [ ] T071 [P] Cross-spec integration smoke test for spec 018 deferred-loading: load a participant whose `capabilities().max_context_tokens=8192` (e.g., the mock `no_tool_model` fixture); confirm deferred-loading partition policy kicks in (consumes `count_tokens()` + `max_context_tokens`)
- [X] T072 [P] Update [src/api_bridge/__init__.py](src/api_bridge/__init__.py) docstring to reflect the adapter-abstraction architecture (remove "API bridge — LiteLLM provider dispatch and format translation" verbiage; replace with "API bridge — pluggable provider adapter abstraction with LiteLLM and mock implementations")
- [X] T073 [P] Update [src/orchestrator/types.py](src/orchestrator/types.py) module docstring to note the `ProviderResponse` re-export shim per T016
- [X] T074 Final FR coverage audit: walk each FR in [spec.md "Functional Requirements"](./spec.md) and confirm at least one task or test exists that exercises it; record findings in [checklists/fr-coverage.md](./checklists/fr-coverage.md) (gitignored if local-only per memory `feedback_audits_as_local_action_plans`)
- [X] T075 Update [specs/020-provider-adapter-abstraction/spec.md](./spec.md) Status to `Implemented YYYY-MM-DD` once all P1+P2 tasks complete (P3 verification optional for Implemented declaration but recommended)
- [X] T076 [US1] Refactor [src/api_bridge/model_limits.py](src/api_bridge/model_limits.py) to remove its inline `import litellm` (currently in `_from_litellm()` at lines 62-69 per pre-feature grep): move the LiteLLM-querying logic into [src/api_bridge/litellm/capabilities.py](src/api_bridge/litellm/capabilities.py) (or a sibling helper under the LiteLLM package); leave `model_limits.py` as a provider-neutral fallback table that `LiteLLMAdapter.capabilities()` consults via the relocated helper. After this task, `model_limits.py` MUST contain no `litellm` references (FR-005 architectural test passes for this file). Coordinate with T031 + T038 (depends on T028, T031, T038)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 standalone; T002, T003, T004 parallel after T001
- **Foundational (Phase 2)**: depends on Setup completion; V16 gate (T005-T011) + ABC + types + registry (T012-T020) + canaries (T021, T022) all complete BEFORE any user story begins
- **User Stories (Phase 3-5)**: all depend on Foundational. US1 (Phase 3) is the v1 deliverable per FR-005's single-PR cutover discipline; US2 (Phase 4) and US3 (Phase 5) build on US1's interface but don't otherwise depend on it (mock adapter implements the same ABC; US3 verifies the abstraction)
- **Polish (Phase 6)**: depends on US1+US2 completion (US3 optional but recommended)

### User Story Dependencies

- **US1 (P1)** (Phase 3): the production-path deliverable. The single-PR cutover (T035-T042) lands the LiteLLM adapter, every consumer migration, and spec 015's circuit-breaker integration in one mergeable unit. US1 is the entire v1 value — without it, the abstraction does nothing.
- **US2 (P2)** (Phase 4): independent of US1's content but reuses the ABC + canonical types from Phase 2. Mock adapter can land as a separate PR after US1 if desired, but the spec's "single-PR cutover" framing recommends bundling.
- **US3 (P3)** (Phase 5): no new code; verifies US1+US2's interface is genuinely abstraction-shaped via architectural assertions and forward-compatibility tests.

### Within Each User Story

- Tests SHOULD be written BEFORE the corresponding implementation tasks (the "failing test as canary" pattern from spec 025)
- Module skeletons before full implementations (T028-T032 are file-level splits of the existing `src/api_bridge/provider.py`; T033 ties them into the `LiteLLMAdapter` class)
- Registry registration after class definition (T034 depends on T033)
- Consumer migration after adapter registration (T035-T038 depend on T034)
- Cleanup AFTER migration (T039 deletes `provider.py` AFTER T028 moves its body and T035-T038 migrate consumers)

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T002, T003, T004)
- V16 gate validators + doc sections marked [P] can run in parallel (T005, T006, T008, T009, T011 in pairs)
- ABC + canonical type dataclasses marked [P] can run in parallel (T013, T014, T015 — T012 first because T013-T015 reference its enum)
- LiteLLM adapter sub-modules marked [P] can run in parallel (T028-T032 — T033 depends on all of them)
- Mock adapter sub-modules marked [P] can run in parallel (T049-T052 — T053 depends on all of them)
- All tests within a user story marked [P] can run in parallel
- Polish tasks marked [P] can run in parallel (T064-T073)

---

## Parallel Example: Phase 2 V16 Gate

```bash
# Five validators + five doc sections can land in parallel after T001-T004:
Task: "Add validate_provider_adapter to src/config/validators.py"
Task: "Add validate_provider_adapter_mock_fixtures_path to src/config/validators.py"
Task: "Add ### SACP_PROVIDER_ADAPTER section to docs/env-vars.md"
Task: "Add ### SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH section to docs/env-vars.md"
Task: "Validator unit tests in tests/test_020_validators.py"

# T007 (append to VALIDATORS tuple) waits for T005, T006
# T010 (run check_env_vars.py) waits for all of T005-T009
```

## Parallel Example: User Story 1 — LiteLLM Adapter Sub-Modules

```bash
# After T012-T020 complete (ABC + types + registry available),
# the LiteLLM adapter's sub-modules can land in parallel:
Task: "Move dispatch logic to src/api_bridge/litellm/dispatch.py"
Task: "Implement _normalize_litellm_error in src/api_bridge/litellm/errors.py"
Task: "Implement _normalize_litellm_stream in src/api_bridge/litellm/streaming.py"
Task: "Implement _compute_capabilities in src/api_bridge/litellm/capabilities.py"
Task: "Implement _count_tokens in src/api_bridge/litellm/tokens.py"

# T033 (LiteLLMAdapter class) depends on all five
# T034 (registry registration) depends on T033
# T035-T040 (consumer migration) depends on T034
# T041 (architectural test passes) depends on T035-T040
```

## Parallel Example: User Story 2 — Mock Adapter Sub-Modules

```bash
# After T012-T020 complete:
Task: "Implement MockFixtureSet + _load in src/api_bridge/mock/fixtures.py"
Task: "Implement _match_fixture in src/api_bridge/mock/fixtures.py"  # same file, different function — sequential
Task: "Implement mock exception classes in src/api_bridge/mock/errors.py"
Task: "Implement _default_stream + _explicit_stream in src/api_bridge/mock/streaming.py"

# T053 (MockAdapter class) depends on all four
# T054 (registry registration) depends on T053
# Sample fixtures (T055-T057) can land in parallel with T053-T054
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (4 tasks, T001-T004)
2. Complete Phase 2: Foundational (18 tasks, T005-T022) — V16 gate, ABC, registry, canaries
3. Complete Phase 3: User Story 1 (21 tasks, T023-T043, plus T076 model_limits refactor in the same PR) — LiteLLM adapter + cutover + spec 015 integration
4. **STOP and VALIDATE**: confirm SC-001 byte-identical regression in CI; confirm FR-005 architectural test passes; confirm spec 015 breaker tests still pass with canonical categories
5. Deploy/demo: the abstraction is in place — every future provider adapter slots in via the v1 interface

### Incremental Delivery

1. Setup + Foundational → Foundation ready (canaries failing as expected)
2. US1 → cutover lands; canaries pass; byte-identical regression confirmed → MVP shippable
3. US2 → mock adapter lands; spec 015 breaker tests can run without network
4. US3 → forward-compatibility verified; ready for future provider adapters
5. Polish → V14 budget verification; cross-spec smoke tests; FR coverage audit

### Parallel Team Strategy

With multiple developers, after Phase 2 completes:

- Developer A: US1 LiteLLM adapter sub-modules + cutover (T028-T042) — the production-path deliverable
- Developer B: US2 mock adapter package (T049-T058) — independent of US1's cutover
- Developer C: US3 forward-compatibility tests (T059-T063) — depends on US1+US2

The single-PR cutover discipline means US1's tasks land in one PR; US2's tasks may land separately or in the same PR; US3's tasks land after US1+US2.

---

## Notes

- [P] tasks = different files OR independent functions in the same file with no shared edit point
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (the architectural-test canary T021 is the canonical example — it MUST initially fail)
- Commit after each task or logical group; do not bundle V16 gate tasks with US1 implementation tasks
- Stop at any checkpoint to validate independently
- Avoid: vague tasks, same-file conflicts during parallel work, cross-story dependencies that break independence
- Per memory `feedback_no_local_refs_in_prs`: in commit messages and PR bodies, list only what's IN the PR — do not name held-back files or future-spec deliverables
- Per memory `feedback_commit_message_style`: short title, high-level summary + one-line bullets, no test inventories, no recon-grade detail
- Per memory `feedback_no_auto_push`: each `git push` requires explicit user approval; do not auto-push after commits

## V16 Deliverable Gate Reminder

T005-T011 land BEFORE any code-path work that consumes the env vars. CI gate `scripts/check_env_vars.py` enforces drift detection; landing the validators + docs first keeps the regression test (SC-001) executable from the start. Per spec FR-013 + Constitution V16, this is non-negotiable.

## Spec 011 Forward-Reference

Per memory `reminder_spec_011_amendments_at_impl_time`, six new specs (022/024/025/027/028/029) carry a forward-ref deferring spec 011 UI FRs to implementation time. Spec 020 is NOT in that list — the adapter abstraction has no UI surface. No spec 011 amendment needed for spec 020.
