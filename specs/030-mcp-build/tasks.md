---
description: "Task list for spec 030 MCP Build implementation"
---

# Tasks: MCP Build — Codebase Restructure, Protocol Implementation, Tool Mapping, OAuth 2.1, and Participant Onboarding Documentation

**Input**: Design documents from `specs/030-mcp-build/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Architectural tests (FR-068 parity, FR-099 token-boundary) AND protocol-compliance tests (FR-067 happy + error path per tool) AND V14 perf-test harnesses are REQUIRED per the spec — not optional. Other unit/integration tests are at implementer discretion within the V7 standards.

**Organization**: Tasks are grouped by user story per the spec's US1–US22 enumeration. Five-phase ordering (Phase 1 → Phase 2+3 co-designed → Phase 4 → Phase 5) per spec §Phase Sequencing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different files, no dependencies — parallelizable
- **[Story]**: US1–US22 mapping
- File paths are absolute or repo-relative

---

## Phase 1: Setup (shared infrastructure)

- [ ] T001 Confirm feature branch `030-mcp-build` is checked out and clean — `git status` → clean; `git branch --show-current` → `030-mcp-build`
- [ ] T002 [P] Confirm research.md, data-model.md, plan.md, quickstart.md, contracts/ are all present in `specs/030-mcp-build/` per the plan structure
- [ ] T003 [P] Confirm CLAUDE.md tech stack reflects the Phase 4 PyJWT addition (update-agent-context.ps1 has been run on this branch)

---

## Phase 2: Foundational (blocking prerequisites — PHASE 1 OF THE SPEC)

**⚠️ CRITICAL**: No Phase 2/3/4 spec work can begin until the rename PR is merged to `main`.

**Purpose**: Execute the Phase 1 (codebase restructure) of the spec — pure refactor with no behavior change. This is foundational because Phases 2/3/4 of the spec depend on `src/participant_api/` + `src/mcp_protocol/` existing.

### Pre-refactor baseline capture

- [ ] T004 Capture pre-refactor test count and passing-assertions count via `pytest --collect-only -q | tail -5` → record in PR description for FR-012 baseline
- [ ] T005 [P] Capture pre-refactor ruff baseline via `ruff check . --statistics` → record for SC-007
- [ ] T006 [P] Run pre-refactor smoke test (both ASGI apps start on 8750 + 8751; `/sse/{session_id}` payload shape recorded) for SC-005, SC-006

### Module rename (US1)

- [ ] T007 [US1] `git mv src/mcp_server/ src/participant_api/` (preserves blame history per FR-001)
- [ ] T008 [US1] Verify `git log --follow src/participant_api/app.py` shows pre-refactor commits (SC-004)
- [ ] T009 [P] [US1] Update all `from src.mcp_server` and `import mcp_server` imports under `src/` → `src.participant_api` (FR-002)
- [ ] T010 [P] [US1] Update all `from src.mcp_server` and `import mcp_server` imports under `tests/` → `src.participant_api` (FR-008)
- [ ] T011 [P] [US1] Update all `from src.mcp_server` imports under `alembic/versions/` → `src.participant_api` (FR-005)
- [ ] T012 [P] [US1] Update all `mcp_server` references under `docs/` (FR-010)
- [ ] T013 [US1] Verify `git grep "mcp_server" -- src/ tests/ docs/ alembic/` returns zero hits (SC-001)
- [ ] T014 [US1] Rename `create_mcp_app` → `create_participant_api_app` in `src/run_apps.py` (FR-003); update entry point callers
- [ ] T015 [US1] Rename `prime_from_mcp_app` → `prime_from_participant_api_app`; add backward-compat alias `prime_from_mcp_app = prime_from_participant_api_app` in `src/participant_api/__init__.py` (FR-004)
- [ ] T016 [US1] Move `/sse/{session_id}` route to `src/participant_api/sse.py` + `src/participant_api/sse_router.py` with zero behavior change (FR-007)

### Reserve mcp_protocol namespace (US3)

- [ ] T017 [US3] Create `src/mcp_protocol/__init__.py` with placeholder docstring indicating Phase 2 will populate (FR-009)
- [ ] T018 [US3] Verify `from src.mcp_protocol import __doc__` resolves and shows placeholder docstring

### Deployment-side audit (US2)

- [ ] T019 [P] [US2] Audit repo-side `compose.yaml` for `mcp_server` path references; update any hits (FR-006)
- [ ] T020 [P] [US2] Audit `.env` (if checked in) for `mcp_server` references; update any hits
- [ ] T021 [P] [US2] Audit `scripts/` and `docker/` directories for `mcp_server` references; update any hits
- [ ] T022 [US2] Add deployment-side migration note to PR description: TrueNAS Dockge stack at `/mnt/.ix-apps/app_mounts/dockge/stacks/sacp/compose.yaml` requires separate manual update (per memory `project_deploy_dockge_truenas`)

### Post-refactor verification

- [ ] T023 Run full pytest suite and capture post-refactor test count + passing-assertions count; match against T004 baseline (FR-012)
- [ ] T024 Run `ruff check .` and compare against T005 baseline; zero new findings (SC-007)
- [ ] T025 Run post-refactor smoke test (both ASGI apps start; `/sse/{session_id}` payload shape matches T006 recording) for SC-005, SC-006
- [ ] T026 Verify `ls src/` shows `participant_api/` + `mcp_protocol/` and does NOT show `mcp_server/` (SC-003)

### Phase 2 closeout preflights

- [ ] T027 Run the seven closeout preflights per `feedback_closeout_preflight_scripts`: traceability, doc-deliverables, audit-label parity, detection-taxonomy parity, migration chain, plus the two newer preflights. All MUST be green before opening the Phase 1 merge PR (FR-013, SC-063)

**Checkpoint**: At this point, Phase 1 of the spec (codebase restructure) is ready to merge. Phases 2/3/4 work CANNOT begin until Phase 1 lands on `main`.

---

## Phase 3: Phase 2 of the spec — MCP Protocol over Streamable HTTP

**Goal**: Implement the MCP wire-format transport, dispatcher, session lifecycle, error model, and protocol-version negotiation pinned to revision 2025-11-25.

**Independent Test**: An `mcp-remote` bridge completes the full handshake (initialize → tools/list → tools/call) against the SACP MCP endpoint using a valid bearer token (SC-010).

### V16 deliverable gate (BEFORE the rest of Phase 3 tasks run)

- [ ] T028 [US4] Add `validate_sacp_mcp_protocol_enabled`, `validate_sacp_mcp_session_idle_timeout_seconds`, `validate_sacp_mcp_session_max_lifetime_seconds`, `validate_sacp_mcp_max_concurrent_sessions` to `src/config/validators.py`; register in `VALIDATORS` tuple (research.md §3, FR-034)
- [ ] T029 [US4] Add six-field sections for the four Phase 2 env vars to `docs/env-vars.md` (FR-034)

### MCP SDK dependency selection

- [ ] T030 [US4] Decision: adopt Python `mcp` SDK pinned per Constitution §6.3 (research.md §1); add the pinned version to `pyproject.toml` / `uv.lock`
- [ ] T031 [US4] Run `uv sync --frozen` and confirm the SDK installs and imports clean

### Protocol layer scaffold

- [ ] T032 [P] [US4] Create `src/mcp_protocol/envelope.py`: JSON-RPC 2.0 envelope shapes (Request, SuccessResponse, ErrorResponse, Notification) + error-code mapping table per FR-019
- [ ] T033 [P] [US4] Create `src/mcp_protocol/errors.py`: shared error-code catalog (`SACP_E_VALIDATION`, `SACP_E_FORBIDDEN`, `SACP_E_NOT_FOUND`, `SACP_E_INTERNAL`, `SACP_E_AUTH`, `SACP_E_RATE_LIMIT`, `SACP_E_SESSION_EXPIRED`, `SACP_E_STEP_UP_REQUIRED`) per FR-055
- [ ] T034 [P] [US4] Create `src/mcp_protocol/session.py`: MCPSession in-memory state per data-model.md Phase 2 section; per-instance dict keyed by `mcp_session_id`; idle-timeout + hard-lifetime checks; concurrent-session cap check (FR-020, FR-027)
- [ ] T035 [P] [US4] Create `src/mcp_protocol/handshake.py`: `initialize` handler — protocol-version negotiation (strict; rejects non-2025-11-25 per research.md §6), capability advertisement (tools + logging only; NO prompts NO resources per FR-032), `Mcp-Session-Id` issuance via `secrets.token_bytes(32).hex()` (FR-015, FR-020)
- [ ] T036 [US4] Create `src/mcp_protocol/dispatcher.py`: `tools/call` boundary per contracts/mcp-tools-call.md — registry lookup, paramsSchema validation, scope check, idempotency check, dispatch, returnSchema validation, audit-log emission (FR-017, FR-053, FR-054, FR-056). Implements the boundary signature from contracts/tool-registry-shape.md (depends on T032, T033)
- [ ] T037 [P] [US4] Create `src/mcp_protocol/discovery.py`: `/.well-known/mcp-server` endpoint per contracts/mcp-discovery-metadata.md — works in both `enabled: true` and `enabled: false` states (FR-024, SC-023)
- [ ] T037B [P] [US7] Create `src/mcp_protocol/ping.py` (or inline in `src/mcp_protocol/handshake.py`): `ping` method handler returns minimal JSON-RPC 2.0 success envelope with no body data beyond protocol-required fields per FR-018; add to the method-dispatch table in `transport.py`
- [ ] T037C [P] [US4] Create `src/mcp_protocol/hooks.py`: `DispatchHook` Protocol + built-in `V14TimingHook` (emits per-stage timing to `routing_log`) + `AuditLogHook` (writes `admin_audit_log` row) per FR-066 + contracts/tool-registry-shape.md; wire both hooks into `dispatcher.py`
- [ ] T038 [P] [US4] Create `src/mcp_protocol/routing.py`: spec 022 cross-instance dispatch integration — at `tools/call` time consult the binding registry; if bound to different instance, forward via HTTP proxy hop with original envelope (FR-023, SC-019)
- [ ] T039 [US4] Create `src/mcp_protocol/transport.py`: Streamable HTTP transport handler — mounts at `/mcp` on the port 8750 ASGI app; FastAPI `APIRouter` integration; rate-limit middleware re-uses spec 019 with per-bearer bucket key (FR-026, FR-028)
- [ ] T040 [US4] Wire `src/mcp_protocol/transport.py` into `src/run_apps.py` `create_participant_api_app` — gated by `SACP_MCP_PROTOCOL_ENABLED` env var; when false, `/mcp` returns HTTP 404 (FR-025, SC-016)
- [ ] T041 [US4] Add startup validator hook: if `SACP_MCP_PROTOCOL_ENABLED=true` AND the SDK import fails OR any of the four Phase 2 env vars are invalid → exit with clear error (FR-031, SC-050)

### Tests (Phase 2 surface) — REQUIRED per spec

- [ ] T042 [P] [US4] `tests/test_mcp_protocol_initialize.py` — happy path; protocol-version negotiation; session-id issuance; capability advertisement (FR-015)
- [ ] T043 [P] [US4] `tests/test_mcp_protocol_session.py` — idle timeout → 404 + -32003; hard lifetime → same; cross-restart loss (FR-021, research §7)
- [ ] T044 [P] [US4] `tests/test_mcp_protocol_errors.py` — JSON-RPC 2.0 compliance: -32700 parse, -32601 method-not-found, -32602 invalid-params, -32001 auth, -32002 rate-limit, -32003 SACP state (FR-019, SC-017)
- [ ] T045 [P] [US4] `tests/test_mcp_protocol_discovery.py` — `enabled: true` shape; `enabled: false` shape; OAuth-metadata-url conditional on Phase 4 (FR-024, SC-023)
- [ ] T046 [P] [US4] `tests/test_mcp_protocol_routing.py` — cross-instance dispatch via spec 022 binding registry; proxy hop preserves envelope (FR-023, SC-019)
- [ ] T047 [P] [US4] `tests/test_mcp_protocol_master_switch.py` — `SACP_MCP_PROTOCOL_ENABLED=false` → `/mcp` returns 404; participant_api unaffected on 8750 (FR-025, SC-016)
- [ ] T048 [P] [US4] `tests/test_mcp_protocol_concurrency_cap.py` — set cap=5; 6th `initialize` returns 503 + Retry-After (FR-027, SC-020)
- [ ] T049 [P] [US4] `tests/test_mcp_protocol_perf.py` — V14 perf harness: 100 concurrent handshakes; assert P95 `initialize` ≤ 500ms, `tools/list` ≤ 100ms, `ping` ≤ 50ms, `tools/call` round-trip ≤ 5s (FR-030, SC-013, SC-014, SC-015)
- [ ] T050 [P] [US4] `tests/test_mcp_protocol_prompts_resources.py` — `prompts/list` and `resources/list` return -32601 (FR-032, SC-021)

### Per-stage timing instrumentation

- [ ] T051 [US4] Add timing labels `mcp_initialize`, `mcp_tools_list`, `mcp_tools_call`, `mcp_ping` to `routing_log` per spec 003 §FR-030 (plan §V14)

### Custom Connector + claude code registration smoke (US5, US6)

- [ ] T052 [US5] Document Custom Connector configuration in `docs/mcp-client-setup-custom-connector.md` — endpoint URL `/mcp`, bearer token slot, Streamable HTTP only (no SSE fallback) per FR-014
- [ ] T053 [US5] Manual smoke test: configure Claude Desktop Pro+ Custom Connector pointing at the endpoint; complete handshake (SC-011)
- [ ] T054 [US6] Document `claude mcp add sacp <url> --token <bearer>` flow in `docs/mcp-client-setup-claude-code.md`
- [ ] T055 [US6] Manual smoke test: register SACP via `claude mcp add`; confirm tools surface in claude code's tool list (SC-012)

### Phase 2 audit logging

- [ ] T056 [US4] Add `admin_audit_log` row emission to every `tools/call` invocation per FR-029 — Phase 2 action code `mcp_tool_called` (generic; per FR-029 this is intentional until the ToolRegistry lands in Phase 3), includes tool name, MCP session id, SACP session id, participant id, dispatch result (SC-018, SC-027)

### MCP error-path use case verification (US7)

- [ ] T057 [P] [US7] Add error-path test cases to `tests/test_mcp_protocol_errors.py` covering each row of contracts/mcp-tools-call.md error table

**Checkpoint**: Phase 2 of the spec is independently mergeable; the MCP endpoint speaks Streamable HTTP and the four protocol-compliance tests + perf harness are green.

---

## Phase 4: Phase 3 of the spec — SACP-to-MCP Tool Mapping

**Goal**: Populate the `ToolRegistry` Phase 2's dispatcher reads. Every public `participant_api` capability becomes a named, JSON-Schema'd, scope-bound MCP tool.

**Independent Test**: Architectural test (FR-068) — every public `participant_api` route has at least one corresponding `RegistryEntry`. Happy + error path tests per tool category (FR-067).

### V16 deliverable gate (BEFORE the rest of Phase 3 tasks run)

- [ ] T058 [US8] Add validator functions for all 14 Phase 3 env vars to `src/config/validators.py`; register in `VALIDATORS` tuple per research.md §3 (FR-069)
- [ ] T059 [US8] Add six-field sections for all 14 Phase 3 env vars to `docs/env-vars.md` (FR-069)

### Registry shape + loader

- [ ] T060 [P] [US8] Create `src/mcp_protocol/tools/registry.py`: type declarations per contracts/tool-registry-shape.md — `ToolDefinition`, `CallerContext`, `ToolDispatch`, `RegistryEntry`, `ToolRegistry`
- [ ] T061 [P] [US8] Create `src/mcp_protocol/tools/__init__.py`: registry loader iterates over per-category modules; calls each `register()` function; filters by enabled-env-var per FR-061
- [ ] T062 [P] [US8] Create `src/mcp_protocol/pagination.py`: opaque base64-encoded JSON cursor per data-model.md Phase 3 section (FR-059)
- [ ] T063 [P] [US8] Create `src/mcp_protocol/idempotency.py`: idempotency-key lookup against `admin_audit_log` with retention horizon from `SACP_MCP_TOOL_IDEMPOTENCY_RETENTION_HOURS` (FR-058, SC-029)

### Per-category tool definition files (parallel)

- [ ] T064 [P] [US8] `src/mcp_protocol/tools/session_tools.py`: `session.create`, `session.update_settings`, `session.archive`, `session.delete`, `session.list`, `session.get` (FR-040, FR-052)
- [ ] T065 [P] [US9] `src/mcp_protocol/tools/participant_tools.py`: `participant.create`, `participant.update`, `participant.remove`, `participant.rotate_token`, `participant.list`, `participant.get`, `participant.inject_message`, `participant.set_routing_preference`, `participant.set_budget` (FR-041, FR-042, FR-045, FR-052)
- [ ] T066 [P] [US10] `src/mcp_protocol/tools/proposal_tools.py`: `proposal.create`, `proposal.cast_vote`, `proposal.close`, `proposal.list` (FR-043)
- [ ] T067 [P] [US10] `src/mcp_protocol/tools/review_gate_tools.py`: `review_gate.list_pending`, `review_gate.approve`, `review_gate.reject`, `review_gate.edit_and_approve` (FR-044)
- [ ] T068 [P] [US11] `src/mcp_protocol/tools/debug_tools.py`: `debug.export_session`, `debug.export_participant_view` — chunked/paginated return per FR-052, FR-059 (FR-046)
- [ ] T069 [P] [US11] `src/mcp_protocol/tools/audit_tools.py`: `admin.get_audit_log` — backed by spec 029 read-side query (FR-047, FR-064)
- [ ] T070 [P] [US11] `src/mcp_protocol/tools/detection_event_tools.py`: `detection_events.list`, `detection_events.detail` — backed by spec 022 read-side query (FR-048, FR-064)
- [ ] T071 [P] [US11] `src/mcp_protocol/tools/scratch_tools.py`: `scratch.list_notes`, `scratch.create_note`, `scratch.update_note`, `scratch.delete_note`, `scratch.promote_to_transcript` — backed by spec 024 (FR-049, FR-064)
- [ ] T072 [P] [US8] `src/mcp_protocol/tools/provider_tools.py`: `provider.list`, `provider.test_credentials` — sovereignty exclusions per FR-084 (FR-050)
- [ ] T073 [P] [US8] `src/mcp_protocol/tools/admin_tools.py`: `admin.list_sessions`, `admin.list_participants`, `admin.transfer_facilitator`, `admin.archive_session`, `admin.mass_revoke_tokens` (FR-051)

### Per-tool dispatch implementation

For each tool defined in T064–T073, implement the `ToolDispatch` callable that bridges to the corresponding `src/participant_api/tools/<router>.py` function. Tasks are bundled per category since dispatch implementations are similar in shape:

- [ ] T074 [US8] Implement dispatch callables for `session_tools.py` — wire to `src/participant_api/tools/session.py` router functions
- [ ] T075 [US9] Implement dispatch callables for `participant_tools.py` — wire to `src/participant_api/tools/participant.py` router functions
- [ ] T076 [US10] Implement dispatch callables for `proposal_tools.py` — wire to `src/participant_api/tools/proposal.py`
- [ ] T077 [US10] Implement dispatch callables for `review_gate_tools.py` — wire to the review-gate flow per spec 002
- [ ] T078 [US11] Implement dispatch callables for `debug_tools.py` — wire to `src/participant_api/tools/debug.py`
- [ ] T079 [US11] Implement dispatch callables for `audit_tools.py` — wire to spec 029 read query
- [ ] T080 [US11] Implement dispatch callables for `detection_event_tools.py` — wire to spec 022 read query
- [ ] T081 [US11] Implement dispatch callables for `scratch_tools.py` — wire to spec 024 routes (stub if spec 024 not yet Implemented; documented exclusion)
- [ ] T082 [US8] Implement dispatch callables for `provider_tools.py` — sovereignty boundary applied per FR-084
- [ ] T083 [US8] Implement dispatch callables for `admin_tools.py`

### AI-accessibility flag enforcement (US12)

- [ ] T084 [US12] Per FR-063, set `aiAccessible=True` on `participant.inject_message`, `proposal.cast_vote`, `participant.set_routing_preference` (on self); set `aiAccessible=False` on `participant.rotate_token` on others, `admin.transfer_facilitator`, all debug-export tools
- [ ] T085 [US12] `tests/test_mcp_tools_ai_access.py` — parameterized: every tool × AI-caller-yes/no × scope-yes/no (SC-034)

### Sponsor scope (FR-065)

- [ ] T086 [US10] Implement sponsor-scope grants in `scope_grant` logic: sponsors get `participant.set_budget` + `participant.rotate_token` for sponsored AI + read tools to inspect sponsored AI state; sponsor scope does NOT grant message-injection on sponsored AI behalf (FR-065)
- [ ] T087 [US10] `tests/test_mcp_tools_sponsor_scope.py` — confirm SC-035

### Architectural tests (REQUIRED per spec)

- [ ] T088 [US8] `tests/test_mcp_tools_parity.py` — enumerate every public `participant_api` router endpoint AND every `RegistryEntry`; assert parity OR documented exclusion (FR-068, SC-036)
- [ ] T089 [US8] `tests/test_mcp_tools_registry_size.py` — registry size invariant (~50 tools); lookup is O(1) (SC-037); assert registry is immutable post-startup (attempt to mutate raises `TypeError` or equivalent — enforces spec §Out of Scope "Hot-reload of the tool registry") (C5 analysis fix)

### Per-category happy + error path tests

For each tool category, one happy-path + one error-path test (FR-067):

- [ ] T090 [P] [US8] `tests/test_mcp_tools_session.py`
- [ ] T091 [P] [US9] `tests/test_mcp_tools_participant.py`
- [ ] T092 [P] [US10] `tests/test_mcp_tools_proposal.py`
- [ ] T093 [P] [US10] `tests/test_mcp_tools_review_gate.py`
- [ ] T094 [P] [US11] `tests/test_mcp_tools_debug.py`
- [ ] T095 [P] [US11] `tests/test_mcp_tools_audit.py`
- [ ] T096 [P] [US11] `tests/test_mcp_tools_detection_events.py`
- [ ] T097 [P] [US11] `tests/test_mcp_tools_scratch.py`
- [ ] T098 [P] [US8] `tests/test_mcp_tools_provider.py`
- [ ] T099 [P] [US8] `tests/test_mcp_tools_admin.py`

### Cross-cutting tests

- [ ] T100 [P] [US8] `tests/test_mcp_tools_idempotency.py` — idempotency-key re-submission returns original result (SC-029)
- [ ] T101 [P] [US8] `tests/test_mcp_tools_pagination.py` — cursor traversal covers full result set in stable order (SC-030)
- [ ] T102 [P] [US8] `tests/test_mcp_tools_category_switches.py` — disabled category hidden from `list_tools`; `call_tool` returns `SACP_E_NOT_FOUND` (SC-032)
- [ ] T103 [P] [US8] `tests/test_mcp_tools_versioning.py` — `session.create.v1` + `session.create.v2` coexist within deprecation horizon (SC-033)
- [ ] T104 [P] [US8] `tests/test_mcp_tools_scope_enforcement.py` — parameterized scope/tool combinations; SC-028
- [ ] T105 [P] [US8] `tests/test_mcp_tools_perf.py` — V14 budgets per category (SC-031)
- [ ] T106 [P] [US8] `tests/test_mcp_tools_audit_invariant.py` — every successful dispatch emits exactly one audit row (SC-027)
- [ ] T107 [P] [US8] `tests/test_mcp_tools_rest_parity.py` — side-by-side REST vs MCP for the same operation produces equivalent persisted state (SC-026)
- [ ] T108 [P] [US8] `tests/test_mcp_tools_schema_coverage.py` — every tool's paramsSchema + returnSchema declares every field with type; every error path enumerated (SC-025)

### FR-057 audit action-code migration (D1 analysis fix)

- [ ] T109B [US8] In `src/mcp_protocol/dispatcher.py`, replace the Phase 2 generic `action='mcp_tool_called'` with the per-tool `action=f'mcp_tool_{tool_name}'` now that the ToolRegistry is populated (FR-057). Add test to `tests/test_mcp_tools_audit_invariant.py` asserting per-tool action codes on every dispatch.

### Phase 3 closeout preflights

- [ ] T109 [US8] Run the seven closeout preflights (FR-013, SC-063); all green before opening Phase 3 merge PR

**Checkpoint**: Phase 3 of the spec is independently mergeable; the tool registry is populated and the architectural + happy/error path tests are green.

---

## Phase 5: Phase 4 of the spec — OAuth 2.1 + PKCE

**Goal**: Layer OAuth 2.1 + PKCE on the MCP endpoint with JWT access tokens + Fernet-encrypted opaque refresh tokens, per-participant token isolation, refresh rotation, discovery metadata, CIMD, scope binding, step-up, AI exclusion, controlled migration off static tokens.

**Independent Test**: End-to-end OAuth flow against the orchestrator completes without manual intervention beyond standard browser interaction (SC-038).

### Sovereignty remediation (BEFORE this phase's `/speckit.tasks` proper — codified per FR-084)

- [ ] T110 [US13] Confirm sovereignty remediation is complete and FR-084 exclusions are codified in `src/mcp_protocol/auth/scope_grant.py` design (BLOCKING precursor per plan §Phase Sequencing)

### V16 deliverable gate (BEFORE the rest of Phase 4 tasks run)

- [ ] T111 [US13] Add validator functions for all 12 Phase 4 env vars (11 from original list + `SACP_MCP_TOKEN_CACHE_TTL_SECONDS` per analysis finding I1 / FR-094 amendment) plus optional `SACP_OAUTH_PREVIOUS_SIGNING_KEY_PATH` to `src/config/validators.py`; register in `VALIDATORS` tuple per research.md §3 (FR-088, FR-094)
- [ ] T112 [US13] Add six-field sections for all 12 Phase 4 env vars (including `SACP_MCP_TOKEN_CACHE_TTL_SECONDS` default 5, range 1–30) to `docs/env-vars.md` (FR-088, FR-094)

### Dependencies

- [ ] T113 [US13] Add PyJWT 2.x pinned per Constitution §6.3 to `pyproject.toml` / `uv.lock` (research.md §2)
- [ ] T114 [US13] Run `uv sync --frozen` and confirm PyJWT installs clean

### Schema migration

- [ ] T115 [US13] Create alembic migration adding the five OAuth tables per data-model.md Phase 4: `oauth_clients`, `oauth_authorization_codes`, `oauth_access_tokens`, `oauth_refresh_tokens`, `oauth_token_families`. Pre-allocate revision slot per `feedback_parallel_merge_sequence_collisions`
- [ ] T116 [US13] Update `tests/conftest.py` schema mirror to include the five new tables per `feedback_test_schema_mirror`

### Auth-server scaffold

- [ ] T117 [P] [US13] Create `src/mcp_protocol/auth/jwt_signer.py`: PyJWT wrapper; ES256 signing; key loaded from `SACP_OAUTH_SIGNING_KEY_PATH`; rotation grace via optional previous-key path (research.md §2)
- [ ] T118 [P] [US13] Create `src/mcp_protocol/auth/pkce.py`: S256 challenge/verifier handling (FR-071); `plain` rejected
- [ ] T119 [P] [US13] Create `src/mcp_protocol/auth/refresh_token_store.py`: Fernet-encrypted opaque refresh-token persistence; SHA-256 hash index; rotation logic (FR-079, FR-081)
- [ ] T120 [P] [US13] Create `src/mcp_protocol/auth/token_family.py`: family tracking; replay detection; family-revocation cascade (FR-079)
- [ ] T121 [P] [US13] Create `src/mcp_protocol/auth/scope_grant.py`: scope-intersection (requested ∩ grantable); FR-084 sovereignty exclusions; scope vocabulary per FR-077
- [ ] T122 [P] [US13] Create `src/mcp_protocol/auth/step_up.py`: `auth_time` freshness check per `SACP_OAUTH_STEP_UP_FRESHNESS_SECONDS` (FR-086)
- [ ] T123 [P] [US13] Create `src/mcp_protocol/auth/client_registration.py`: CIMD fetcher with bounded timeout (10s) + size (256 KiB) + allowlist hosts (FR-076, FR-098)
- [ ] T124 [US13] Create `src/mcp_protocol/auth/authorization_server.py`: `/authorize` endpoint per contracts/oauth-authorize.md (FR-072, FR-089). Depends on T118, T121, T123
- [ ] T125 [US13] Create `src/mcp_protocol/auth/token_endpoint.py`: `/token` endpoint per contracts/oauth-token.md — authorization_code + refresh_token grants (FR-073, FR-079, FR-097). Depends on T117, T119, T120
- [ ] T126 [US13] Create `src/mcp_protocol/auth/revocation_endpoint.py`: `/revoke` endpoint per contracts/oauth-revoke.md (FR-074, FR-092). Depends on T119, T120
- [ ] T127 [P] [US13] Create `src/mcp_protocol/auth/discovery_metadata.py`: `/.well-known/oauth-protected-resource` per contracts/oauth-discovery-metadata.md (FR-075)
- [ ] T128 [US13] Wire all auth endpoints into the port 8750 ASGI app; gate on `SACP_OAUTH_ENABLED` (FR-087, SC-050)

### Token boundary enforcement (FR-099)

- [ ] T129 [US13] Refactor `src/mcp_protocol/dispatcher.py` to validate JWT access tokens via the per-instance cache (TTL 5s per plan); cache miss falls back to DB lookup against `oauth_access_tokens` (FR-094)
- [ ] T130 [US13] Audit: confirm no code path under `src/` outside `src/mcp_protocol/auth/` accepts an OAuth token directly (FR-099, SC-051)

### Static-token migration (US14)

- [ ] T131 [US14] In dispatcher, when a static-token participant makes their first MCP request post-Phase-4-ship, return a migration prompt embedded in the success/error response data per FR-082
- [ ] T132 [US14] After `SACP_OAUTH_STATIC_TOKEN_GRACE_DAYS` from ship date, static tokens stop validating on the MCP endpoint per FR-083 — implementation pin in this task: track per-participant first-prompted date in a new column on `participants` (or a sidecar table); migrate the column via the same alembic migration as T115
- [ ] T133 [US14] Confirm static tokens continue working on the SACP participant API regardless of MCP grace period (FR-083)

### Revocation propagation (US15)

- [ ] T134 [US15] Add management-endpoint surface for user-initiated revocation per FR-074; this is the same `/revoke` endpoint exposed via the Web UI flow
- [ ] T135 [US15] Implement connection-close logic per FR-092 — within `SACP_OAUTH_REVOCATION_PROPAGATION_SECONDS` (default 5)
- [ ] T136 [US15] `tests/test_mcp_oauth_revocation_propagation.py` — assert revoked token closes open MCP transport connection within SLA (SC-045)

### Audit logging (US16)

- [ ] T137 [US16] Emit `admin_audit_log` rows for every token lifecycle event per FR-085: `token_issued`, `token_refreshed`, `token_revoked`; failed events emit `security_event` row with action codes per spec
- [ ] T138 [US16] Confirm `tools/call` rows include OAuth scope claims in human-readable form for forensic review

### AI-participant exclusion (US17)

- [ ] T139 [US17] In `authorization_server.py`, refuse to start the flow if subject is `participant.kind == 'ai'` (FR-089); emit `security_event` row; return `access_denied`
- [ ] T140 [US17] `tests/test_mcp_oauth_ai_exclusion.py` (SC-046)

### Tests (Phase 4 surface) — REQUIRED per spec

- [ ] T141 [P] [US13] `tests/test_mcp_oauth_authorize.py` — full flow happy + error paths (FR-070, FR-072)
- [ ] T142 [P] [US13] `tests/test_mcp_oauth_token.py` — authorization_code + refresh_token grants; replay detection (FR-073, FR-079)
- [ ] T143 [P] [US15] `tests/test_mcp_oauth_revoke.py` — token + family revocation (FR-074)
- [ ] T144 [P] [US13] `tests/test_mcp_oauth_discovery.py` — metadata shape per RFC + MCP authorization spec (FR-075, SC-043)
- [ ] T145 [P] [US13] `tests/test_mcp_oauth_pkce.py` — S256 enforced; `plain` rejected (FR-071, SC-042)
- [ ] T146 [P] [US14] `tests/test_mcp_oauth_refresh_rotation.py` — atomic issue+revoke; replay → family revocation + security_event (FR-079, SC-041)
- [ ] T147 [P] [US13] `tests/test_mcp_oauth_step_up.py` — destructive actions reject stale tokens (FR-086, SC-047)
- [ ] T148 [P] [US13] `tests/test_mcp_oauth_cimd.py` — fuzz hostile inputs (oversized, malformed, redirect-chain) (FR-076, FR-098, SC-044)
- [ ] T149 [P] [US14] `tests/test_mcp_oauth_static_migration.py` — grace window honored; post-grace rejected (FR-082, FR-083, SC-039)
- [ ] T150 [P] [US16] `tests/test_mcp_oauth_audit.py` — every lifecycle event has corresponding audit row (FR-085, SC-052)
- [ ] T151 [P] [US13] `tests/test_mcp_oauth_token_boundary.py` — architectural test FR-099 / SC-051
- [ ] T152 [P] [US13] `tests/test_mcp_oauth_token_isolation.py` — concurrent participants; one's compromise doesn't affect another (SC-040)
- [ ] T153 [P] [US13] `tests/test_mcp_oauth_multi_session.py` — one human subject participates in multiple sessions; tokens isolated per session (FR-091)
- [ ] T154 [P] [US13] `tests/test_mcp_oauth_cross_instance.py` — revocation on instance A visible on instance B within 30s (FR-094, SC-049)
- [ ] T155 [P] [US13] `tests/test_mcp_oauth_perf.py` — authorize + token endpoints P95 ≤ 200ms (FR-095, SC-048)

### Per-IP rate-limit on OAuth endpoints (C3 analysis fix)

- [ ] T155B [US13] Wire spec 019 per-IP rate-limit middleware onto `/authorize`, `/token`, and `/revoke` endpoints in `src/mcp_protocol/auth/` per FR-093. Add `tests/test_mcp_oauth_per_ip_rate_limit.py` asserting per-IP bucket isolation on each endpoint.

### Session-claim mismatch enforcement (C4 analysis fix)

- [ ] T155C [US13] Add `tests/test_mcp_oauth_session_claim.py`: token's `session_id` claim mismatches with target tool-call session → dispatcher returns `SACP_E_FORBIDDEN` per FR-080.

### Phase 4 closeout preflights

- [ ] T156 [US13] Run the seven closeout preflights; all green before opening Phase 4 merge PR (FR-087, SC-063)

**Checkpoint**: Phase 4 of the spec is independently mergeable; OAuth 2.1 + PKCE is live on the MCP endpoint.

---

## Phase 6: Phase 5 of the spec — Participant Onboarding Documentation

**Goal**: Ship `docs/participant-onboarding.md`, `docs/participant-onboarding-windows.md`, `docs/participant-onboarding-macos.md` with the four-field bundle template, version headers, troubleshooting matrix, and cross-references to Phases 1–4.

**Independent Test**: A non-Spike Windows + macOS participant onboards end-to-end following ONLY the docs in ≤ 15 minutes (SC-053, SC-054).

### Cross-platform overview (US18)

- [ ] T157 [P] [US18] Create `docs/participant-onboarding.md` with version header (FR-117) — SACP Phase + Last Updated + Tested Against
- [ ] T158 [US18] Add facilitator-creates-session step (FR-100) — both pre-Phase-3 REST form and post-Phase-3 `session.create` MCP-tool form
- [ ] T159 [US18] Add facilitator-issues-participant-token step (FR-101) — token-shown-once contract; rotation as recovery path
- [ ] T160 [US18] Add onboarding bundle template (FR-102) — four fields in declared order; masked-display block
- [ ] T161 [US18] Add bearer token format documentation (FR-104) — opaque ≥ 32 chars; Bearer header
- [ ] T162 [US18] Add session_id vs participant_id distinction (FR-105) — both 12-char hex; 403 troubleshooting entry
- [ ] T163 [US18] Add endpoint URL format (FR-103) — current `/sse/{session_id}`; future `/mcp`
- [ ] T164 [US18] Add token rotation policy (FR-106) — end-to-end flow; grace-window semantics
- [ ] T165 [US18] Add disconnect-reconnect behavior (FR-107, US22) — stateless on reconnect; catch-up path via spec 010 export
- [ ] T166 [US18] Add troubleshooting matrix (FR-116) — 401/403/404/timeout with root-cause lists and fix paths; cite 2026-05-12 debug session by date per V19 (SC-057)
- [ ] T167 [US18] Add CSRF/origin documentation (FR-115) — current SACP participant API has no Origin/Referer requirement; Phase 4 tightens
- [ ] T168 [US18] Add cross-references to Phases 1–4 (FR-120) — forward-looking notes
- [ ] T169 [US18] Add Phase-3-OAuth migration section structurally (FR-118) — heading + placeholder; content-fills when Phase 4 lands
- [ ] T170 [US18] Add Linux out-of-scope note (FR-122)
- [ ] T171 [US18] Omit mobile entirely (FR-123)

### Windows-specific doc (US19)

- [ ] T172 [P] [US19] Create `docs/participant-onboarding-windows.md` with version header
- [ ] T173 [US19] Document 8.3 short-path for `npx.cmd` (FR-108) — `dir /x` cmd; cmd.exe /C space-bug explanation
- [ ] T174 [US19] Document env-var workaround for `--header` (FR-109) — `Authorization:${VAR}` no space; complete sample
- [ ] T175 [US19] Document PowerShell vs cmd.exe quoting differences (FR-110) — working invocations for both
- [ ] T176 [US19] Document Windows Defender first-run scan stall (FR-111) — wait-it-out option + exclusion path + risk note
- [ ] T177 [US19] Document CRLF vs LF in `claude_desktop_config.json` (FR-112) — VS Code, Notepad++, Notepad save-as-LF
- [ ] T178 [US19] Add sample `claude_desktop_config.json` Windows shape per FR-119 — 8.3 short-path + env-var pattern + LF
- [ ] T179 [US19] Document Windows reconnect-after-sleep with Defender re-scan (FR-107, US22)

### macOS-specific doc (US20)

- [ ] T180 [P] [US20] Create `docs/participant-onboarding-macos.md` with version header
- [ ] T181 [US20] Document config-file location (FR-113) — `~/Library/Application Support/Claude/`; hidden-Library visibility toggle
- [ ] T182 [US20] Document `xattr -d com.apple.quarantine` handling (FR-114) — exact invocation + risk note
- [ ] T183 [US20] Document first-run permission prompts (FR-114)
- [ ] T184 [US20] Document Apple Silicon vs Intel notes inline (research.md §10 confirms unified macOS doc)
- [ ] T185 [US20] Add sample `claude_desktop_config.json` macOS shape per FR-119

### Token rotation mid-session (US21)

- [ ] T186 [US21] Document end-to-end rotation flow per FR-106 — facilitator rotate-tool, new bundle, env-var update, restart
- [ ] T187 [US21] Document 401 troubleshooting path per FR-116 cross-link

### Redaction policy (FR-121) + secret-scanner allowlist

- [ ] T188 [US18] Confirm sample tokens use `SACP_DOC_EXAMPLE_<32-char alphanumeric>` prefix; add prefix to `.2ms.yaml` allowed-values per research.md §11
- [ ] T189 [US18] Confirm session_id placeholder `000000000000`; endpoint URL placeholder `http://orchestrator.example:8750`

### Tests (doc validation) — REQUIRED per spec

- [ ] T190 [P] [US18] Run secret-scanner on doc files; assert zero hits (SC-062)
- [ ] T191 [P] [US18] JSON-parse the sample config blocks via `jq .`; assert parseable (SC-060)
- [ ] T192 [P] [US18] Structural check: every doc has version header (SC-058)
- [ ] T193 [P] [US18] Structural check: Phase 4 OAuth migration section is present (even when empty) (SC-059)
- [ ] T194 [P] [US18] Cross-reference resolution: every cross-link in the docs resolves to an existing spec/file (SC-061)
- [ ] T195 [P] [US18] Troubleshooting matrix has all four entries (401, 403, 404, Timeout) with at least one cited root cause each (SC-057)

### Walk-through validation (US19, US20)

- [ ] T196 [US19] Walk-through: non-Spike Windows participant follows docs end-to-end; stopwatch ≤ 15 min; record in doc's commit history (SC-053)
- [ ] T197 [US19] Confirm zero unresolved 401/403/404/timeout at end of Windows walk-through (SC-055)
- [ ] T198 [US20] Walk-through: non-Spike macOS participant follows docs end-to-end; stopwatch ≤ 15 min (SC-054)
- [ ] T199 [US20] Confirm zero unresolved 401/403/404/timeout at end of macOS walk-through (SC-056)

### Phase 5 closeout preflights

- [ ] T200 [US18] Run the seven closeout preflights; all green before opening Phase 5 merge PR (SC-063)

**Checkpoint**: Phase 5 of the spec is independently mergeable; v1 docs ship.

---

## Phase 7: Polish & Cross-cutting concerns

- [ ] T201 [P] Documentation pass: update `docs/sacp-design.md` to reference the renamed module + the MCP layer per Phase 1/2 reality
- [ ] T202 [P] Add Phase 1/2/3/4 entries to `docs/env-vars.md` table of contents
- [ ] T203 [P] Update CLAUDE.md if any further tech-stack drift surfaced during implementation
- [ ] T204 [P] Run V14 perf-test harness across all phases; document P95 numbers in spec.md's "Implementation notes" section (post-merge)
- [ ] T205 Cross-link: spec 011 amendment per `reminder_spec_011_amendments_at_impl_time` if Web-UI-touching changes surface
- [ ] T206 Run quickstart.md scenarios end-to-end on a fresh deploy
- [ ] T207 Final security review: every architectural test (FR-068, FR-099) passes on the merge PR

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies
- **Phase 2 (Foundational = Spec Phase 1, the rename)**: Depends on Phase 1
- **Phase 3 (Spec Phase 2)**: Depends on Phase 2 completion (rename merged to main)
- **Phase 4 (Spec Phase 3)**: Depends on Phase 2 completion; CO-DESIGNED with Phase 3 — registry-shape contracts in [contracts/tool-registry-shape.md](./contracts/tool-registry-shape.md) MUST hold; may merge in either order
- **Phase 5 (Spec Phase 4)**: Depends on Phases 3 + 4 stable AND sovereignty remediation complete
- **Phase 6 (Spec Phase 5)**: Can run in parallel with Phases 3–5; v1 ships against existing SACP-native surface
- **Phase 7 (Polish)**: Depends on all phases

### Within Each Phase

- V16 deliverable gate (validator + docs/env-vars.md) MUST complete BEFORE other tasks in that phase
- Schema migrations (Phase 4 only) MUST complete BEFORE auth-server scaffold uses the tables
- Architectural tests are CI-blocking — MUST be green at merge

### Parallel Opportunities

- Phase 2 tasks T009–T012 (per-directory import updates) can run in parallel
- Phase 3 contract scaffold tasks T032–T038 are per-file and can run in parallel
- Phase 4 per-category tool-definition tasks T064–T073 are per-file and can run in parallel
- Phase 4 per-category dispatch implementations T074–T083 can run in parallel
- Phase 4 per-category tests T090–T099 can run in parallel
- Phase 5 auth-scaffold tasks T117–T123 are per-file and can run in parallel
- Phase 5 tests T141–T155 are per-file and can run in parallel
- Phase 6 sub-docs (US18, US19, US20) can be drafted in parallel
- All `[P]`-marked tasks are explicitly parallelizable

### Per-PR Strategy

Each spec phase ships as its own PR:
1. **PR 1**: Phase 1 (rename) — T001–T027
2. **PR 2**: Phase 2 (MCP protocol) — T028–T057 + T037B (ping) + T037C (hooks)
3. **PR 3**: Phase 3 (tool mapping) — T058–T109 + T109B (FR-057 action-code migration) (can race PR 2)
4. **PR 4**: Phase 4 (OAuth) — T110–T156 + T155B (per-IP rate-limit) + T155C (session-claim test) (after PRs 2+3 + sovereignty remediation)
5. **PR 5**: Phase 5 (onboarding docs) — T157–T200 (can race the others; v1)
6. **PR 6 (optional)**: Phase 5 doc updates after Phase 4 lands — content-fills T169 reserved section

Pre-allocate validator slots + alembic revision IDs at PR-spawn time per `feedback_parallel_merge_sequence_collisions`.

### Stooges parallelism

For the per-category tool-definition + dispatch tasks (T064–T083), the categories are sufficiently independent that they can be assigned to parallel agents (Stooges trigger). Suggested split:
- Moe: session + admin + provider categories
- Larry: participant + proposal + review_gate categories
- Curly: debug + audit + detection_events + scratch categories

---

## Implementation Strategy

### MVP First (Phase 1 of spec only — the rename)

1. Complete Phase 1 + Phase 2 of this tasks file (T001–T027)
2. Merge the rename to main
3. **STOP and VALIDATE**: confirm zero behavior change; old SACP clients continue working
4. Deploy

### Incremental delivery

1. PR 1 (rename) — MVP, lands first
2. PR 5 (onboarding docs v1) — can ship in parallel with PRs 2/3/4; describes current state
3. PR 2 (MCP protocol) + PR 3 (tool mapping) — co-designed; either order
4. PR 4 (OAuth) — after PRs 2+3 stable + sovereignty remediation
5. PR 6 (doc updates) — content-fills reserved OAuth section after PR 4 lands

### Parallel team strategy

If staffed across multiple developers:
- Developer A: Phase 1 rename (single contributor; small, blocking)
- After rename: Developers B, C, D parallel on Phase 3 (protocol), Phase 4 (tool mapping), Phase 6 (docs)
- After Phase 3 + 4 stable: Developer A picks up Phase 5 (OAuth)
- Sovereignty remediation lane runs in parallel with Phases 3+4 since it doesn't touch the same files

---

## Notes

- `[P]` tasks = different files, no dependencies
- `[Story]` label maps each task to spec.md user stories (US1–US22) for traceability
- Each phase's merge PR runs the seven closeout preflights per `feedback_closeout_preflight_scripts`
- Validator slots + alembic revisions pre-allocated per `feedback_parallel_merge_sequence_collisions`
- Architectural tests (FR-068 parity + FR-099 token-boundary) are CI-blocking
- V14 perf-test harnesses are CI-blocking
- V16 deliverable gate (validator + docs/env-vars.md) is enforced per-phase BEFORE the rest of the phase's tasks
- Per the spec's clarifications (Session 2026-05-13), the five highest-impact pivots are locked: `participant_api` rename target, `src/mcp_protocol/` namespace, `/mcp` mount on port 8750, `domain.action` snake_case tool names, JWT access + opaque-Fernet refresh tokens
- Per memory `feedback_dont_declare_phase_done`: phase status is the operator's call, not the model's
