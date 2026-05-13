# Implementation Plan: MCP Build — Codebase Restructure, Protocol Implementation, Tool Mapping, OAuth 2.1, and Participant Onboarding Documentation

**Branch**: `030-mcp-build` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/030-mcp-build/spec.md`

## Summary

Five-phase build correcting the long-misnamed `src/mcp_server/` module (no MCP protocol code there — it is SACP's participant-facing FastAPI surface) and shipping actual MCP protocol support. Phase 1 is a pure refactor (`git mv` rename → `src/participant_api/`, reserve `src/mcp_protocol/` namespace). Phase 2 implements MCP Streamable HTTP transport per spec revision 2025-11-25 (SSE intentionally skipped — the revision deprecates it). Phase 3 maps every public `participant_api` capability to a named, JSON-Schema'd, scope-bound MCP tool via a startup-loaded `ToolRegistry`. Phase 4 layers OAuth 2.1 + PKCE on the MCP endpoint with JWT access tokens + Fernet-encrypted opaque refresh tokens, per-participant token isolation, refresh rotation with family-replay detection, discovery metadata, Client ID Metadata Documents, scope binding to Phase 3's vocabulary, step-up for destructive actions, and a controlled migration off static tokens. Phase 5 ships three onboarding docs (cross-platform overview + Windows-specific gotchas + macOS-specific gotchas) with a four-field bundle template, version headers, and a troubleshooting matrix.

Technical approach lock-ins from the Session 2026-05-13 clarifications: module rename target is `participant_api`, reserved namespace is `src/mcp_protocol/`, transport binding is `/mcp` on existing port 8750, tool naming is `domain.action` snake_case, token format is JWT access + opaque-Fernet-encrypted refresh.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest (all existing). Phase 2 adds either the Python `mcp` SDK (pinned per §6.3) OR a direct Streamable HTTP wire-protocol implementation — decision in [research.md §1](./research.md). Phase 4 adds a JWT library (PyJWT 2.x candidate, pinned per §6.3) for access-token signing; `cryptography` (Fernet) already a project dependency via spec 023 carries the refresh-token at-rest encryption per [research.md §2](./research.md).
**Storage**: PostgreSQL 16. **No schema changes for Phase 1, Phase 2, or Phase 3.** Phase 4 ships one alembic migration adding the OAuth-state tables (`oauth_clients`, `oauth_authorization_codes`, `oauth_access_tokens`, `oauth_refresh_tokens`, `oauth_token_families`) detailed in [data-model.md](./data-model.md). The `tests/conftest.py` schema mirror is updated alongside per `feedback_test_schema_mirror`. Spec 022's `session_instance_bindings` table (or Redis-pubsub variant) is re-used by Phase 2 cross-instance dispatch — no new table introduced for that surface.
**Testing**: pytest (existing); new test modules under `tests/test_mcp_protocol_*.py`, `tests/test_mcp_tools_*.py`, `tests/test_mcp_oauth_*.py`. The architectural tests called out in FR-068 (participant_api ↔ MCP-tool parity) and FR-099 (OAuth-token validation locality) ship as CI-blocking test cases.
**Target Platform**: Linux server (Debian slim-bookworm in container per Constitution §6.8). MCP clients are cross-platform (Claude Desktop on Windows/macOS, claude code CLI on Windows/macOS/Linux, Cursor, custom agents).
**Project Type**: Single project (matches existing repo layout — no frontend/backend split for this work; Phase 1 leaves the React UMD frontend untouched).
**Performance Goals**: Phase 2: `initialize` P95 ≤ 500ms, `tools/list` P95 ≤ 100ms, `tools/call` P95 ≤ 5s, `ping` P95 ≤ 50ms, `/.well-known/mcp-server` P95 ≤ 20ms. Phase 3: dispatch overhead P95 ≤ 5ms (protocol → dispatcher → registry-lookup → scope-check); per-tool budgets in tool metadata. Phase 4: authorization endpoint P95 ≤ 200ms, token endpoint P95 ≤ 200ms, revocation endpoint P95 ≤ 100ms, per-dispatch token validation P95 ≤ 5ms (cache-hit path), revocation propagation ≤ 5 seconds end-to-end. Phase 5 doc-quality: Windows + macOS onboarding ≤ 15 minutes each.
**Constraints**: V14 budgets enforced as contracts (per §12). V15 fail-closed on every new env var. V16 validator + docs/env-vars.md entry required BEFORE `/speckit.tasks` is run for each phase introducing env vars. V17 transcript canonicity: OAuth + MCP audit events go to `admin_audit_log` and `security_events`, NEVER to the message transcript. V18 traceability: tokens carry `sub`, `client_id`, `scope`, `auth_time`, `iat`, `exp`, `jti`. V19 evidence markers: troubleshooting matrix entries cite the 2026-05-12 debug session by date. V12 topology applicability: Phases 1–5 apply to topologies 1–6; topology 7 (MCP-to-MCP peer) is explicitly NOT applicable.
**Scale/Scope**: Single orchestrator instance handles ≤ 100 concurrent MCP sessions (`SACP_MCP_MAX_CONCURRENT_SESSIONS` default 100, beyond which `initialize` returns 503 + Retry-After). Tool registry size: ~50 tools across 10 categories at v1 ship per FR-040 through FR-052. OAuth scope vocabulary: 4 role scopes + 10 tool-category scopes = 14 distinct scope claims (FR-077).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### V1 — Sovereignty preserved
- API-key isolation: Phase 4 refresh tokens are per-participant; FR-084 enumerates that facilitator scope MUST NOT grant access to participant BYOK credentials or sponsored-AI wallets. The sovereignty remediation completes BEFORE Phase 4 `/speckit.tasks`.
- Model choice independence: untouched. MCP tools are an alternative dispatch surface for the SACP participant API; the LiteLLM bridge and per-participant provider config are unchanged.
- Budget autonomy: untouched. `participant.set_budget` is sponsor-scoped per FR-065 — sponsor invokes on the sponsored AI's budget; the sponsor scope does NOT grant message-injection on the sponsored AI's behalf.
- Prompt privacy: untouched. MCP tools dispatch through the existing participant_api routers; the AI security pipeline (spec 007) gates AI-generated content at the participant_api layer per FR-017's "same auth, rate-limit, and audit hooks" requirement.
- Exit freedom: untouched. Static tokens continue working on the SACP participant API indefinitely (FR-083); only the MCP endpoint migrates to OAuth.
- **Result**: PASS.

### V2 — No cross-phase leakage
- Phase 4 OAuth is the Constitution §10 Phase 3 roadmap deliverable; this build is the work item that satisfies §10.
- All MCP work is Phase 3 capability.
- Phase 4 spec items (A2A federation, Agent Card discovery) are NOT introduced — Phase 4 of THIS spec is OAuth, scoped to the MCP endpoint only.
- **Result**: PASS.

### V3 — Security hierarchy respected
- The architectural test in FR-099 asserts OAuth-token validation is exclusively in `src/mcp_protocol/auth/` — no readability shortcut bypasses the boundary.
- PKCE S256-only (FR-071); `plain` rejected. Implicit and ROPC grants rejected (FR-070).
- Refresh-token replay revokes the entire family (FR-079) with a `security_event` row — fail-fast over fail-quietly.
- **Result**: PASS.

### V4 — Facilitator powers bounded
- FR-084 enumerates facilitator-scope EXCLUSIONS: no access to other participants' BYOK credentials, no access to non-sponsored participants' budgets. The sovereignty remediation codifies these exclusions in the scope claim semantics.
- **Result**: PASS.

### V5 — Transparency maintained
- Every MCP `tools/call` invocation emits an `admin_audit_log` row (FR-029, FR-057, SC-018, SC-027). Failed dispatches due to validation/scope/business-rule errors are also logged.
- Every OAuth token lifecycle event (issuance, refresh, revocation) emits an `admin_audit_log` row AND a `security_event` row on failure (FR-085, FR-096, SC-052).
- **Result**: PASS.

### V6 — Graceful degradation
- Phase 2 master switch `SACP_MCP_PROTOCOL_ENABLED=false` returns HTTP 404 on `/mcp` while SACP participant_api on the same port continues normally (FR-025, SC-016).
- Phase 3 per-category switches hide tools from `list_tools` and reject `call_tool` with `SACP_E_NOT_FOUND` (FR-061, SC-032) — operator can selectively disable categories without killing the whole MCP surface.
- Phase 5 troubleshooting matrix (FR-116) is the explicit graceful-degradation surface for participant-facing failures.
- **Result**: PASS.

### V7 — Coding standards met
- 25/5 limits, type hints, pre-commit hooks, banned functions — enforced via existing ruff + pre-commit framework. Phase 1 is a pure rename and surfaces zero new style issues.
- Banned code-style patterns per `feedback_code_style_banned_patterns` apply: no restating-the-code comments, no generic naming tells, no one-liner-wrapping functions, no generic try/catch, no interfaces with one implementation.
- **Result**: PASS.

### V8 — Data security enforced
- Refresh tokens Fernet-encrypted at rest (FR-081, spec 023 pattern). Token lookup via per-token hash for indexing.
- Refresh tokens never appear in audit-log rows except as scrubbed identifiers (FR-085).
- CIMD fetcher bounded by network timeout (10s default) AND document size (256 KiB default) per FR-098.
- **Result**: PASS.

### V9 — Log integrity preserved
- All audit rows go to `admin_audit_log` (append-only); the application DB role retains INSERT + SELECT only on log tables. No change to log-write privileges.
- **Result**: PASS.

### V10 — AI security pipeline enforced
- FR-017: MCP `tools/call` dispatches flow through the same auth, rate-limit, and audit hooks the participant_api uses today. The AI security pipeline (spec 007 `_validate_and_persist`) at the participant_api layer is the gating point for AI-generated content; the MCP protocol layer does NOT bypass it.
- **Result**: PASS.

### V11 — Supply chain controls enforced
- Phase 1 introduces zero new dependencies.
- Phase 2 likely adds the Python `mcp` SDK; if so, pinned per §6.3 (specific version, not range). If the team chooses direct-wire implementation, V11 is trivially satisfied. Settled in [research.md §1](./research.md).
- Phase 4 adds a JWT library (PyJWT 2.x candidate); pinned per §6.3. `cryptography` (Fernet) is already a project dependency via spec 023.
- Phase 3 and Phase 5 introduce zero new dependencies.
- **Result**: PASS.

### V12 — Topology compatibility verified
- All five phases apply to topologies 1–6 (orchestrator-mediated).
- Topology 7 (MCP-to-MCP peer) is explicitly NOT applicable; each phase carves it out.
- Cross-instance routing within topologies 1–6 reuses spec 022's binding registry (FR-023).
- **Result**: PASS.

### V13 — Use case coverage acknowledged
- Every V13 use case has at least one tool surface (Phase 3), one onboarding path (Phase 5), AND benefits from OAuth on the MCP endpoint where applicable (Phase 4). Primary beneficiaries called out: §3 Consulting Engagement, §5 Technical Review and Audit, §1 Distributed Software Collaboration.
- **Result**: PASS.

### V14 — Performance budgets specified and instrumented
- Per-phase P95 budgets enumerated in Technical Context above. Phases 2/3/4 contribute V14 budgets; Phase 5 contributes documentation-driven onboarding-time budgets (SC-053/054).
- Per-stage timings emit to `routing_log` per spec 003 §FR-030 with new timing labels (`mcp_initialize`, `mcp_tools_list`, `mcp_tools_call`, `mcp_ping`, plus per-tool labels from the registry).
- **Result**: PASS.

### V15 — Security pipeline fail-closed
- All new env vars (Phase 2's four, Phase 3's per-category enables + tunables, Phase 4's eleven) fail closed at startup. Invalid values cause the orchestrator process to exit with a clear error naming the offending var (FR-031, FR-069, FR-087, SC-050).
- **Result**: PASS.

### V16 — Configuration validated at startup
- Each new env var introduced by Phases 2/3/4 MUST have a validator function in `src/config/validators.py` registered in the `VALIDATORS` tuple AND a corresponding section in `docs/env-vars.md` with the six standard fields BEFORE `/speckit.tasks` is run for that phase. Phases 1 and 5 introduce zero new env vars.
- See [research.md §3](./research.md) for the V16 deliverable mapping and the per-env-var validator-and-docs checklist.
- **Result**: PASS at plan time; deliverable gate satisfied at `/speckit.tasks` time.

### V17 — Transcript canonicity respected
- OAuth flow events + MCP audit rows go to `admin_audit_log` AND `security_events`, NEVER to the message transcript (FR-096). The transcript is the SACP session messages; the protocol-layer invocation log is forensic, not conversational.
- **Result**: PASS.

### V18 — Derived artifacts are traceable
- Phase 4 tokens carry claims sufficient to trace back to the canonical participant record AND the canonical scope-grant decision: `sub`, `client_id`, `scope`, `auth_time`, `iat`, `exp`, `jti` (FR-097).
- Phase 3 tool dispatch results that denormalize from canonical source rows (audit-log read views, detection-event-history views) carry source-range metadata in their `returnSchema` where the source allows it.
- **Result**: PASS.

### V19 — Evidence and judgment markers present
- Phase 5 troubleshooting matrix entries cite evidence from real debug sessions; the 2026-05-12 debug session is one such source, cited by date (FR-116, SC-057).
- Phases 1–4 are evidence-rooted in the 2026-05-12 misnamed-module discovery, with the rename, protocol implementation, tool mapping, and OAuth migration all flowing from that single anchored finding.
- **Result**: PASS.

## Project Structure

### Documentation (this feature)

```text
specs/030-mcp-build/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── mcp-initialize.md
│   ├── mcp-tools-list.md
│   ├── mcp-tools-call.md
│   ├── mcp-discovery-metadata.md
│   ├── oauth-authorize.md
│   ├── oauth-token.md
│   ├── oauth-revoke.md
│   ├── oauth-discovery-metadata.md
│   └── tool-registry-shape.md
└── tasks.md             # Phase 2 output (/speckit.tasks command — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── participant_api/                 # PHASE 1: renamed from src/mcp_server/ via `git mv`
│   ├── __init__.py
│   ├── app.py                       # FastAPI app (renamed)
│   ├── middleware.py                # auth + rate-limit middleware (unchanged)
│   ├── rate_limiter.py              # spec 019 rate limiter (unchanged)
│   ├── sse.py                       # /sse/{session_id} SACP turn-event stream (unchanged shape)
│   ├── sse_router.py                # router wiring for /sse (unchanged)
│   └── tools/                       # existing FastAPI HTTP routers
│       ├── admin.py
│       ├── debug.py
│       ├── detection_events.py
│       ├── facilitator.py
│       ├── participant.py
│       ├── proposal.py
│       ├── provider.py
│       ├── scratch.py               # spec 024 surface when it lands
│       └── session.py
│
├── mcp_protocol/                    # PHASE 1: empty namespace reserved; PHASES 2–4 populate
│   ├── __init__.py                  # Phase 1 ships placeholder docstring; no other code
│   │
│   ├── transport.py                 # PHASE 2: Streamable HTTP transport handler
│   ├── session.py                   # PHASE 2: MCP session lifecycle, Mcp-Session-Id issuance
│   ├── dispatcher.py                # PHASE 2: tools/call boundary; param validation; scope check; audit
│   ├── envelope.py                  # PHASE 2: JSON-RPC 2.0 envelope shapes + error mapping
│   ├── handshake.py                 # PHASE 2: initialize handler + capability advertisement
│   ├── discovery.py                 # PHASE 2: /.well-known/mcp-server endpoint
│   ├── errors.py                    # PHASE 2 + 3: shared error-code catalog
│   ├── routing.py                   # PHASE 2: spec 022 cross-instance dispatch integration
│   ├── pagination.py                # PHASE 3: opaque-cursor encoding/decoding
│   ├── idempotency.py               # PHASE 3: idempotency-key persistence + lookup
│   │
│   ├── tools/                       # PHASE 3: tool registry + per-category dispatch bridges
│   │   ├── __init__.py              # ToolRegistry loader + iteration helpers
│   │   ├── registry.py              # ToolDefinition + ToolDispatch types
│   │   ├── session_tools.py         # session.create, session.update_settings, session.archive, ...
│   │   ├── participant_tools.py     # participant.create, participant.update, inject_message, ...
│   │   ├── proposal_tools.py        # proposal.create, proposal.cast_vote, ...
│   │   ├── review_gate_tools.py     # review_gate.list_pending, approve, reject, edit_and_approve
│   │   ├── debug_tools.py           # debug.export_session, debug.export_participant_view
│   │   ├── audit_tools.py           # admin.get_audit_log
│   │   ├── detection_event_tools.py # detection_events.list, detection_events.detail
│   │   ├── scratch_tools.py         # scratch.list_notes, create_note, update_note, ...
│   │   ├── provider_tools.py        # provider.list, provider.test_credentials
│   │   └── admin_tools.py           # admin.list_sessions, list_participants, transfer_facilitator
│   │
│   └── auth/                        # PHASE 4: OAuth 2.1 + PKCE surface
│       ├── __init__.py
│       ├── authorization_server.py  # /authorize endpoint
│       ├── token_endpoint.py        # /token endpoint (authorization_code + refresh_token grants)
│       ├── revocation_endpoint.py   # /revoke endpoint (RFC 7009)
│       ├── discovery_metadata.py    # /.well-known/oauth-protected-resource
│       ├── pkce.py                  # S256 challenge/verifier handling
│       ├── client_registration.py   # Client ID Metadata Document fetcher + validator
│       ├── jwt_signer.py            # PyJWT wrapper for access-token signing/verification
│       ├── refresh_token_store.py   # Fernet-encrypted refresh-token persistence + rotation
│       ├── token_family.py          # family tracking + replay detection
│       ├── scope_grant.py           # scope-intersection (requested ∩ grantable-to-user)
│       └── step_up.py               # step-up freshness check for destructive actions
│
├── run_apps.py                      # PHASE 1: rename create_mcp_app → create_participant_api_app
└── config/
    └── validators.py                # PHASES 2/3/4 add validator functions per V16

alembic/
└── versions/
    └── <slot_NNN>_oauth_state_tables.py  # PHASE 4: oauth_clients, oauth_authorization_codes,
                                          # oauth_access_tokens, oauth_refresh_tokens,
                                          # oauth_token_families (no Phase 1/2/3 migrations)

tests/
├── conftest.py                      # PHASE 4: mirror oauth_* tables per feedback_test_schema_mirror
├── test_mcp_protocol_initialize.py  # PHASE 2
├── test_mcp_protocol_tools_list.py  # PHASE 2
├── test_mcp_protocol_tools_call.py  # PHASE 2
├── test_mcp_protocol_errors.py      # PHASE 2 (compliance harness)
├── test_mcp_protocol_session.py     # PHASE 2 (lifecycle + idle timeout)
├── test_mcp_protocol_discovery.py   # PHASE 2 (/.well-known/mcp-server)
├── test_mcp_protocol_routing.py     # PHASE 2 (spec 022 cross-instance)
├── test_mcp_tools_session.py        # PHASE 3 (per-category happy + error paths)
├── test_mcp_tools_participant.py    # PHASE 3
├── test_mcp_tools_proposal.py       # PHASE 3
├── test_mcp_tools_review_gate.py    # PHASE 3
├── test_mcp_tools_debug.py          # PHASE 3
├── test_mcp_tools_audit.py          # PHASE 3
├── test_mcp_tools_detection_events.py  # PHASE 3
├── test_mcp_tools_scratch.py        # PHASE 3
├── test_mcp_tools_provider.py       # PHASE 3
├── test_mcp_tools_admin.py          # PHASE 3
├── test_mcp_tools_parity.py         # PHASE 3 (FR-068 architectural test)
├── test_mcp_tools_idempotency.py    # PHASE 3
├── test_mcp_tools_pagination.py     # PHASE 3
├── test_mcp_oauth_authorize.py      # PHASE 4
├── test_mcp_oauth_token.py          # PHASE 4
├── test_mcp_oauth_revoke.py         # PHASE 4
├── test_mcp_oauth_discovery.py      # PHASE 4
├── test_mcp_oauth_pkce.py           # PHASE 4
├── test_mcp_oauth_refresh_rotation.py    # PHASE 4 (family replay detection)
├── test_mcp_oauth_step_up.py        # PHASE 4
├── test_mcp_oauth_cimd.py           # PHASE 4 (fuzz hostile inputs)
├── test_mcp_oauth_ai_exclusion.py   # PHASE 4 (FR-089)
├── test_mcp_oauth_static_migration.py    # PHASE 4 (grace window)
├── test_mcp_oauth_token_boundary.py # PHASE 4 (FR-099 architectural test)
└── test_mcp_oauth_audit.py          # PHASE 4 (audit-row invariants)

docs/
├── env-vars.md                      # PHASES 2/3/4 append per-env-var entries (six-field shape)
├── participant-onboarding.md        # PHASE 5: cross-platform overview + troubleshooting matrix
├── participant-onboarding-windows.md     # PHASE 5: Windows-specific gotchas
└── participant-onboarding-macos.md  # PHASE 5: macOS-specific gotchas

compose.yaml                         # PHASE 1: audit + update `mcp_server` references
.env                                 # PHASE 1: audit + update `mcp_server` references (if any)
```

**Structure Decision**: Single project. Phase 1 is `git mv` rename only — every move preserves blame history per FR-001. Phase 2 populates the empty `src/mcp_protocol/` namespace reserved by Phase 1. Phase 3 populates `src/mcp_protocol/tools/`. Phase 4 populates `src/mcp_protocol/auth/`. Phase 5 ships three docs at `docs/` root (NOT nested under `docs/onboarding/`). The Web UI under port 8751 stays out of the rename — it is `src/web_ui/` (existing) and continues calling the renamed `prime_from_participant_api_app()` helper.

## Phase Sequencing

Per spec §Cross-References — A → B+C (co-designed) → D → E:

1. **Phase 1 (codebase restructure)**: Blocks Phases 2/3/4. None can begin until the namespace rename is on `main`. This is a single PR; tests must match pre- and post-refactor (FR-012); deployment-side audit per FR-006.
2. **Phase 2 (MCP protocol over Streamable HTTP)** + **Phase 3 (SACP-to-MCP tool mapping)**: Co-designed; B's dispatcher signature MUST match C's `ToolDispatch` shape. May merge in either order so long as the registry-shape contracts in [contracts/tool-registry-shape.md](./contracts/tool-registry-shape.md) hold. Each phase is independently mergeable into `main`.
3. **Phase 4 (OAuth 2.1 + PKCE)**: Requires Phases 2 and 3 stable AND sovereignty remediation completing. The sovereignty remediation (FR-084 exclusions) codifies in the scope claim semantics BEFORE Phase 4 `/speckit.tasks` runs.
4. **Phase 5 (participant onboarding docs)**: Can ship v1 in parallel with Phases 1–4. v1 documents the current SACP-native participant API surface; the Phase-3-OAuth migration section in `docs/participant-onboarding.md` is structurally reserved at v1 ship (FR-118) and content-filled when Phase 4 lands.

**Deliverable gating (V16)**: Each phase introducing env vars MUST complete its `src/config/validators.py` validator + `docs/env-vars.md` six-field section BEFORE `/speckit.tasks` is run for that phase. Phase 1 + Phase 5 introduce zero env vars; gate is trivially satisfied.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified.

No Constitution Check violations. All thirteen V-rules (V1 through V19, excluding V2/V11 counted separately in §12) pass at plan time. The Phase 4 design choices most likely to trip a future audit are:

- **JWT access tokens with 30-second cache TTL**: Trades slightly delayed revocation (≤ 30s) for stateless per-dispatch validation. Documented in research.md §2 with the alternative (always-DB) considered.
- **CIMD fetcher network access**: Phase 4 introduces an outbound HTTP fetch (the orchestrator fetching the client's CIMD URL). Bounded by network timeout + size + allowed-hosts allowlist (`SACP_OAUTH_CIMD_ALLOWED_HOSTS`). Same posture as spec 020's outbound LiteLLM provider calls; no new attack surface category.
- **In-memory tool registry without hot reload**: Adding a new tool requires a deploy (spec §Out of Scope). Trade-off accepted to keep the registry shape simple and the audit trail clean — every tool present at startup is present in the audit-log row's `available_tools` enumeration.

These are design choices, not constitution violations; they live in research.md alongside the alternatives considered.
