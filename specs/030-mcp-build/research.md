# Research: MCP Build (Phase 0)

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-05-13

This file resolves the open technology choices the plan defers. The Session 2026-05-13 spec clarifications already locked the five highest-impact pivots (module rename target `participant_api`, reserved namespace `src/mcp_protocol/`, transport binding `/mcp` on port 8750, tool naming `domain.action` snake_case, token format JWT + opaque-Fernet refresh). This research file covers the remaining technology + integration decisions whose resolution unblocks `/speckit.tasks`.

## §1 — MCP wire-protocol implementation: Python SDK vs. direct implementation

**Question**: Phase 2 implements the MCP Streamable HTTP transport per spec revision 2025-11-25. Should the implementation rely on the Python `mcp` SDK (the official Anthropic-maintained client/server library) or implement the wire protocol directly against the spec text?

**Decision**: Adopt the Python `mcp` SDK as the v1 implementation substrate, pinned per Constitution §6.3 to a specific version (not a range). Direct-wire implementation is the fallback if SDK + protocol-revision drift force a fork.

**Rationale**:
- The MCP spec is evolving; revision 2025-11-25 deprecated SSE in favor of Streamable HTTP and the SDK's release cadence is currently matched to spec revisions. Tracking the spec via SDK upgrades is cheaper than tracking it via manual wire-protocol edits.
- The SDK ships the JSON-RPC 2.0 envelope handling, the `initialize` capability negotiation shape, and the Streamable HTTP transport state machine. Reimplementing these surfaces is high-effort and high-error-rate work that doesn't differentiate SACP.
- Pinning to a specific version (V11 compliance) means an SDK regression doesn't auto-deploy; the version-bump PR is the explicit review surface.
- The SDK does not enforce SACP's audit-log emission, scope binding, or dispatcher routing — those layers stay in `src/mcp_protocol/` per the plan's project structure. The SDK is the wire-format component only, not an application framework.

**Alternatives considered**:
- **Direct wire-protocol implementation**: Lower dependency footprint (V11 trivially satisfied), full control over the envelope handling and the Streamable HTTP state machine. Rejected because (a) the implementation effort is non-trivial and not on the SACP critical path, (b) the test surface to match the SDK's correctness is itself substantial, (c) the spec revision pace makes this a recurring tax.
- **Hybrid (SDK for envelope, custom transport)**: Considered but rejected — the SDK's transport implementation IS the substantial-value piece; the envelope handling is the lighter-weight part. Reversing the dependency boundary loses the SDK's main benefit.

**V11 follow-up**: Pin the SDK version at `/speckit.tasks` time. Add the version-bump policy to `docs/dependency-policy.md` (if not already): SDK upgrades require an explicit task and a manual smoke test against the Phase 2 protocol-compliance test harness BEFORE the version bump merges.

## §2 — JWT library + refresh-token at-rest encryption

**Question**: Phase 4 issues JWT-signed access tokens (per Session 2026-05-13 clarification) and Fernet-encrypted opaque refresh tokens (per FR-081 and spec 023). Which JWT library, and what is the key-management posture?

**Decision**:
- **JWT library**: PyJWT 2.x, pinned per Constitution §6.3. Library choice driven by: (a) maintained, (b) supports RS256/ES256 asymmetric signing, (c) zero hard dependency on `cryptography` beyond what's already in the project via spec 023, (d) no known supply-chain advisories at pin time.
- **Signing algorithm**: ES256 (ECDSA with P-256 + SHA-256). Smaller token size than RS256 and the curve is widely supported by MCP clients. The signing key is loaded from `SACP_OAUTH_SIGNING_KEY_PATH` (V16 env var).
- **Key rotation policy**: A single active signing key at any time; key rotation is operator-driven (out of scope for v1 — manual restart of the orchestrator picks up the new key). The token validation logic accepts the previous-active key for a configurable grace window. **NOTE**: A separate `SACP_OAUTH_PREVIOUS_SIGNING_KEY_PATH` env var supports the rotation grace window; if unset, only the active key validates.
- **Refresh-token encryption**: Reuse the spec 023 Fernet pattern. Refresh tokens are generated as opaque random 256-bit values; the cleartext is presented to the client once at issuance and the Fernet-encrypted form is stored in `oauth_refresh_tokens.encrypted_token`. The refresh-token lookup index is the SHA-256 hash of the cleartext, stored in `oauth_refresh_tokens.token_hash` — this allows constant-time lookup without storing the cleartext.

**Rationale**:
- PyJWT is the de facto Python JWT library (broad ecosystem use, mature). Alternatives like `python-jose` are slower-moving and have had supply-chain advisories in recent history.
- ES256 over RS256 because: smaller tokens (~50% smaller signature) traverse the network faster, and the P-256 curve is supported by every modern client. RS256 is the alternative if a client compatibility issue surfaces — the JWT library swap is small.
- Reusing the Fernet pattern from spec 023 avoids introducing a second encryption boundary; the operator manages one key (the Fernet key) for both API-key encryption (spec 023) and refresh-token encryption (this spec).
- The SHA-256 hash lookup pattern is the standard OAuth refresh-token shape (RFC 6749 Section 10.4): the token endpoint computes the hash on every refresh request, indexes into the table, then decrypts the matched row to validate.

**Alternatives considered**:
- **All-JWT (refresh tokens also JWT)**: Rejected because revocation becomes the recurring concern — JWT refresh tokens are bearer tokens that can't be invalidated short of a deny-list, and a deny-list re-introduces the DB-round-trip the JWT was meant to avoid. Opaque refresh + DB lookup is the standard pattern.
- **Database-stored access tokens (no JWT)**: Rejected because every `tools/call` invocation would then require a DB round-trip to validate the access token, blowing the FR-095 P95 ≤ 200ms budget. JWT enables stateless validation with a 30-second per-instance cache TTL (FR-094) bounding the revocation propagation latency.
- **HS256 (symmetric signing)**: Rejected because the secret would need to be available to every orchestrator instance for validation; horizontal scaling becomes a key-distribution problem. ES256's asymmetric pattern allows one signing key on the issuer and a public-key validation surface on every instance.

## §3 — V16 deliverable mapping per phase

**Question**: Each phase introducing env vars MUST complete its `src/config/validators.py` validator + `docs/env-vars.md` six-field section BEFORE `/speckit.tasks` is run for that phase. What is the per-env-var mapping?

**Decision**: The new env vars introduced by this spec, with their validator stubs and `docs/env-vars.md` sections, are pre-allocated in the deliverable checklist below. Each entry must complete BEFORE the phase's `/speckit.tasks` run. Phase 1 + Phase 5 introduce zero env vars (trivially satisfied).

### Phase 2 (4 env vars)

| Env Var | Type | Default | Range | Fail-Closed Semantics | Validator Slot |
|---|---|---|---|---|---|
| `SACP_MCP_PROTOCOL_ENABLED` | bool | `false` | `true`/`false` | startup-exit on non-bool | `validate_sacp_mcp_protocol_enabled` |
| `SACP_MCP_SESSION_IDLE_TIMEOUT_SECONDS` | int | `1800` | 60–86400 | startup-exit on out-of-range | `validate_sacp_mcp_session_idle_timeout_seconds` |
| `SACP_MCP_SESSION_MAX_LIFETIME_SECONDS` | int | `86400` | 600–604800 | startup-exit on out-of-range | `validate_sacp_mcp_session_max_lifetime_seconds` |
| `SACP_MCP_MAX_CONCURRENT_SESSIONS` | int | `100` | 1–10000 | startup-exit on out-of-range | `validate_sacp_mcp_max_concurrent_sessions` |

### Phase 3 (14 env vars)

| Env Var | Type | Default | Range | Validator Slot |
|---|---|---|---|---|
| `SACP_MCP_TOOL_SESSION_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_session_enabled` |
| `SACP_MCP_TOOL_PARTICIPANT_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_participant_enabled` |
| `SACP_MCP_TOOL_PROPOSAL_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_proposal_enabled` |
| `SACP_MCP_TOOL_REVIEW_GATE_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_review_gate_enabled` |
| `SACP_MCP_TOOL_DEBUG_EXPORT_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_debug_export_enabled` |
| `SACP_MCP_TOOL_AUDIT_LOG_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_audit_log_enabled` |
| `SACP_MCP_TOOL_DETECTION_EVENTS_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_detection_events_enabled` |
| `SACP_MCP_TOOL_SCRATCH_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_scratch_enabled` |
| `SACP_MCP_TOOL_PROVIDER_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_provider_enabled` |
| `SACP_MCP_TOOL_ADMIN_ENABLED` | bool | `true` | bool | `validate_sacp_mcp_tool_admin_enabled` |
| `SACP_MCP_TOOL_IDEMPOTENCY_RETENTION_HOURS` | int | `24` | 1–168 | `validate_sacp_mcp_tool_idempotency_retention_hours` |
| `SACP_MCP_TOOL_DEPRECATION_HORIZON_DAYS` | int | `90` | 7–365 | `validate_sacp_mcp_tool_deprecation_horizon_days` |
| `SACP_MCP_TOOL_PAGINATION_DEFAULT_SIZE` | int | `50` | 1–1000 | `validate_sacp_mcp_tool_pagination_default_size` |
| `SACP_MCP_TOOL_PAGINATION_MAX_SIZE` | int | `500` | 10–10000 | `validate_sacp_mcp_tool_pagination_max_size` |

### Phase 4 (11 env vars)

| Env Var | Type | Default | Range | Validator Slot |
|---|---|---|---|---|
| `SACP_OAUTH_ENABLED` | bool | `false` | bool | `validate_sacp_oauth_enabled` |
| `SACP_OAUTH_ACCESS_TOKEN_TTL_MINUTES` | int | `60` | 5–1440 | `validate_sacp_oauth_access_token_ttl_minutes` |
| `SACP_OAUTH_REFRESH_TOKEN_TTL_DAYS` | int | `30` | 1–365 | `validate_sacp_oauth_refresh_token_ttl_days` |
| `SACP_OAUTH_AUTH_CODE_TTL_SECONDS` | int | `60` | 10–600 | `validate_sacp_oauth_auth_code_ttl_seconds` |
| `SACP_OAUTH_CLIENT_REGISTRATION_MODE` | enum | `allowlist` | `open`/`allowlist`/`closed` | `validate_sacp_oauth_client_registration_mode` |
| `SACP_OAUTH_STATIC_TOKEN_GRACE_DAYS` | int | `90` | 0–365 | `validate_sacp_oauth_static_token_grace_days` |
| `SACP_OAUTH_STEP_UP_FRESHNESS_SECONDS` | int | `300` | 30–3600 | `validate_sacp_oauth_step_up_freshness_seconds` |
| `SACP_OAUTH_REVOCATION_PROPAGATION_SECONDS` | int | `5` | 1–60 | `validate_sacp_oauth_revocation_propagation_seconds` |
| `SACP_OAUTH_SIGNING_KEY_PATH` | path | (none) | readable file | `validate_sacp_oauth_signing_key_path` |
| `SACP_OAUTH_FAILED_PKCE_THRESHOLD` | int | `10` | 1–1000 | `validate_sacp_oauth_failed_pkce_threshold` |
| `SACP_OAUTH_CIMD_ALLOWED_HOSTS` | csv-of-host | (empty=all) | valid hostnames | `validate_sacp_oauth_cimd_allowed_hosts` |

Plus the optional `SACP_OAUTH_PREVIOUS_SIGNING_KEY_PATH` for the rotation grace window (validator `validate_sacp_oauth_previous_signing_key_path`).

**Pre-allocate validator slots per `feedback_parallel_merge_sequence_collisions`**: When Phase 2 + Phase 3 PRs race, both add entries to the `VALIDATORS` tuple. Pre-allocate the slots in the PR-spawn prompts so GitHub auto-merge doesn't silently collide them. The slot order is fixed at this research-doc commit time: Phase 2 vars first (in the order above), then Phase 3 vars, then Phase 4 vars.

## §4 — Cross-instance dispatch (spec 022 binding registry integration)

**Question**: When an MCP client connects to instance A and `tools/call` targets a SACP session bound to instance B, how does the dispatch route cross-instance?

**Decision**: Re-use spec 022's `session_instance_bindings` table (or its Redis pub/sub variant per spec 022's research-resolved choice — final choice ships at spec 022 task time). The MCP dispatcher consults the binding registry at `tools/call` time; if the bound instance is different from the current one, the dispatch is forwarded transparently (HTTP proxy hop to the bound instance with the original MCP envelope). The client sees no change; the audit-log row records the cross-instance hop.

**Rationale**:
- Spec 022 already invests in this binding mechanism for participant-API request routing. The same registry serves MCP request routing.
- No new dependency or pattern is introduced; the MCP `routing.py` module is a thin client of the spec 022 binding-lookup API.
- The cross-instance HTTP proxy hop adds ~20–50ms to the dispatch path in the common case; this fits inside the FR-030 `tools/call` P95 ≤ 5s budget.

**Alternatives considered**:
- **Per-MCP-session sticky routing**: At `initialize` time, the load balancer (or DNS) routes the MCP client to the instance owning the target SACP session. Rejected because (a) the SACP session may not exist yet at `initialize` time, (b) load balancers don't speak the protocol layer, (c) sticky routing breaks under load shedding.
- **Redis pub/sub broadcast on every `tools/call`**: Rejected — broadcasts every dispatch to every instance, wasting work. The binding registry's targeted lookup is the right granularity.

## §5 — Phase 1 backward-compat alias retention

**Question**: The `prime_from_mcp_app()` helper is renamed to `prime_from_participant_api_app()`. How long is the backward-compat alias retained?

**Decision**: One release. The alias is added to `src/participant_api/__init__.py` as `prime_from_mcp_app = prime_from_participant_api_app`, with a release-notes entry flagging the upcoming removal. No deprecation warning at import time (noise on an internal helper).

**Rationale**:
- The helper is internal to the Web UI integration boundary; no external consumers exist outside `src/web_ui/`.
- A one-release alias gives one release-cycle window for any external operator script or local development branch to update.
- Permanent retention would be code debt with no benefit; immediate removal forces a sync-up cost on the Web UI integration PR if it merges separately.

**Alternatives considered**:
- **Immediate removal**: Cleaner but forces the Web UI integration to ship in the same PR as Phase 1. Rejected because Phase 1 should be a clean rename PR with zero behavior change.
- **Permanent alias**: Code debt, no benefit. Rejected.

## §6 — Phase 2 protocol-version negotiation behavior

**Question**: The spec pins to MCP revision 2025-11-25. What happens when a client negotiates an older or newer version in the `initialize` handshake?

**Decision**: Strict rejection. The `initialize` response carries the negotiated protocol version 2025-11-25; clients requesting a different version receive a JSON-RPC 2.0 error with a clear message naming the supported version. No graceful downgrade.

**Rationale**:
- The MCP spec's protocol versioning is intended to support multiple concurrent versions over time, but v1 of the SACP MCP implementation is one version only.
- Graceful downgrade would require shipping multiple protocol versions in code; the wire-format differences across revisions are non-trivial.
- Strict rejection is the safer posture — the client receives a clear actionable error rather than silently degrading to a behavior the server didn't actually implement.

**Alternatives considered**:
- **Graceful downgrade**: Rejected — would require maintaining multiple protocol versions in code; v1 ships one revision.
- **Negotiate to closest supported**: Rejected — the MCP spec doesn't define a "closest supported" semantic.

## §7 — Phase 2 idle session expiry behavior

**Question**: When an MCP session goes idle past `SACP_MCP_SESSION_IDLE_TIMEOUT_SECONDS`, what does the server return on the next request to that session?

**Decision**: HTTP 404 (session unknown). The client is expected to re-handshake with `initialize`. The 404 response carries a JSON-RPC 2.0 error envelope with code -32003 (SACP state) and `data.reason = "mcp_session_expired"`.

**Rationale**:
- HTTP 404 is the semantically correct response — the `Mcp-Session-Id` header no longer maps to any active session.
- The `-32003` SACP-state code + `data.reason` pattern preserves forensic continuity per FR-019.
- The re-handshake path is symmetric with the cold-start case; the client doesn't need to track expiration locally.

**Alternatives considered**:
- **HTTP 401 (re-auth)**: Rejected — the auth posture didn't fail; the session expired. Conflating the two error modes confuses client retry logic.
- **HTTP 410 (gone)**: Considered — semantically more precise than 404 for "this session ID was valid but expired". Rejected because most HTTP clients treat 404 and 410 the same way; the marginal precision isn't worth the client-side surprise.

## §8 — Phase 3 cross-spec tool surface dependency direction

**Question**: Specs 022, 024, and 029 ship read-side surfaces that become MCP tools per FR-064. Does Phase 3 of this build depend on those specs being Implemented, or do they expose MCP tools themselves?

**Decision**: Phase 3 of this build declares the MCP tools wrapping the spec 022 / 024 / 029 surfaces. Each tool's `ToolDispatch` callable depends on the source spec being Implemented (otherwise the dispatch is a stub returning `SACP_E_NOT_FOUND`). The specs 022/024/029 themselves do NOT add MCP tooling.

**Rationale**:
- Centralizes the MCP tool registry in `src/mcp_protocol/tools/`. Per FR-039 the registry is the source of truth Phase 2's dispatcher reads; spreading tool definitions across multiple modules diffuses the audit surface.
- Specs 022/024/029 are read-side surfaces; their authors aren't necessarily MCP-protocol-aware. Centralizing the MCP wrapping in this spec keeps the protocol concerns in one place.
- The `SACP_MCP_TOOL_<CATEGORY>_ENABLED` switches per FR-061 give the operator the lever to disable tool categories whose source specs aren't yet Implemented.

**Alternatives considered**:
- **Each source spec ships its own MCP tooling**: Rejected — diffuses the registry, complicates the audit, and forces specs not otherwise touching the MCP protocol to introduce MCP-layer code.
- **Phase 3 blocks on 022/024/029 reaching Implemented**: Rejected — Phase 3 can ship with stub dispatches for unImplemented source surfaces, and the per-category switches let the operator hide unready tools from `list_tools`.

## §9 — Phase 4 client registration mode default

**Question**: `SACP_OAUTH_CLIENT_REGISTRATION_MODE` accepts `open` / `allowlist` / `closed`. Default value?

**Decision**: `allowlist`. The orchestrator accepts CIMD submissions but only registers clients whose CIMD URLs are on the operator's pre-approved allowlist. The allowlist is operator-managed (out of band) and audited.

**Rationale**:
- `open` is too permissive for a v1 ship — any client on the internet could register. SACP is a small, operator-managed deployment; the v1 client population is bounded (Claude Desktop, claude code, Cursor, custom agents per operator-authorized listing).
- `closed` is too restrictive — the operator would need to manually pre-register every client, defeating the value of CIMD.
- `allowlist` is the middle path: CIMD discovery still works, but the operator gates the registration step.

**Alternatives considered**:
- **`open` as default**: Rejected — security posture too loose.
- **`closed` as default**: Rejected — operational friction too high.

## §10 — Phase 5 doc location convention

**Question**: Three onboarding docs at `docs/` root vs. `docs/onboarding/` subdirectory?

**Decision**: Three docs at `docs/` root, named `participant-onboarding.md`, `participant-onboarding-windows.md`, `participant-onboarding-macos.md`. No nested subdirectory.

**Rationale**:
- The existing `docs/` layout is flat — env-vars.md, dependency-policy.md, etc. all sit at root. A new `docs/onboarding/` subdirectory introduces a hierarchy convention not present in the existing tree.
- Three docs is below the threshold where a subdirectory pays off in navigation. Phase 5 v1 ships three docs; later additions (Linux, mobile) are explicitly out of scope per FR-122 / FR-123.
- The cross-references between docs (FR-120) are simpler with flat paths than nested ones.

**Alternatives considered**:
- **`docs/onboarding/` subdirectory**: Rejected — premature hierarchy for three docs.
- **Single combined doc**: Rejected — platform-specific gotchas are extensive enough that a single doc becomes unwieldy. The Phase 5 scope explicitly carves Windows + macOS into separate docs.

## §11 — Phase 5 sample config redaction policy implementation

**Question**: FR-121 specifies placeholder tokens use `SACP_DOC_EXAMPLE_<32-char alphanumeric>`. How does this interact with the repo-side secret scanner?

**Decision**: The `SACP_DOC_EXAMPLE_` prefix is added to `.2ms.yaml` allowed-values as a recognized placeholder pattern. The scanner will not flag values matching the prefix. The session_id placeholder `000000000000` is also allowed via the same mechanism. The endpoint URL placeholder `http://orchestrator.example:8750` uses a reserved-for-documentation TLD (`.example`) and is not flagged.

**Rationale**:
- The repo's pre-commit + pre-push secret scanners (gitleaks + 2MS) flag realistic-looking tokens. Adding the prefix to `.2ms.yaml` is the documented escape valve per the CLAUDE.md "Triaging a blocked push" section.
- The prefix is recognizable as a placeholder to both the scanner and a human reader, satisfying FR-121's "value is recognizable as a placeholder" requirement.
- The `.example` TLD is reserved by IANA for documentation use; no real host can claim it.

**Alternatives considered**:
- **Generic `<your-token-here>` angle-bracket markers**: Rejected — looks like a literal value in a copy-paste flow; a participant may not realize it's a placeholder. The prefix pattern is unambiguous.
- **Real-format tokens with allowlist entries**: Rejected — every example token would need its own allowlist entry; high maintenance.

## Open questions deferred to `/speckit.tasks` time

These are decisions whose resolution is best done with the concrete task list in hand, not at research-doc time:

- **Phase 3 tool-name final enumeration**: The plan calls out the 10 tool categories and FR-040 through FR-052 list the surface coverage. The exact name list lands in the per-tool tasks (one task per tool definition).
- **Phase 4 step-up freshness threshold (5 minutes vs other values)**: Drafted as 5 minutes in FR-086; the value is operator-tunable via `SACP_OAUTH_STEP_UP_FRESHNESS_SECONDS`. Default decision lands in the task creating the env-var validator.
- **Phase 5 doc walk-through measurement procedure**: The SC-053/054 ≤ 15-minute target is measured at doc-update time. The exact measurement procedure (who runs it, what environment, what counts as "complete") lands in the task for the walk-through itself.

These are not gates on `/speckit.tasks`; they ARE the kinds of decisions tasks naturally encode.
