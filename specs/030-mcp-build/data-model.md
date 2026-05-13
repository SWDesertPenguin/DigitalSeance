# Data Model: MCP Build (Phase 1)

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-05-13

This file enumerates the in-memory and DB-resident data shapes introduced by the five-phase build. Phase 1 introduces zero new shapes (pure refactor). Phase 2 + Phase 3 introduce in-memory shapes only (no schema change). Phase 4 ships the OAuth-state schema migration. Phase 5 introduces documentation shapes only.

## Phase 1 — No data shape changes

Phase 1 is a pure refactor (`git mv` rename). No new entities, no new persistence, no new in-memory shapes. The existing `participants`, `messages`, `routing_log`, `admin_audit_log`, `convergence_log`, `security_events`, `sessions` (and any spec-022 / spec-023 / spec-024 / spec-029 surfaces shipped before Phase 1) are unchanged.

## Phase 2 — In-memory MCP protocol state

### MCPSession (in-memory)

Session-scoped state for an active MCP protocol session. NOT persisted to the DB — sessions are short-lived (idle timeout 30 min default, max lifetime 24h default) and the operational cost of DB-persisting them outweighs the benefit.

| Field | Type | Source | Notes |
|---|---|---|---|
| `mcp_session_id` | `bytes` (256-bit) | Cryptographic random at `initialize` time | Opaque to client; per FR-020 |
| `created_at` | `datetime` (UTC) | Server time at `initialize` | |
| `last_activity_at` | `datetime` (UTC) | Updated on every request | Idle-timeout check reads this |
| `bound_sacp_session_id` | `str` | Caller's `session_id` claim or first `tools/call` target | Binding established at first tool dispatch |
| `bound_participant_id` | `str` | Caller's `participant_id` claim (from bearer token in Phase 2; from JWT `sub` in Phase 4) | |
| `bearer_token_id` | `str` | Hash of the bearer token presented at `initialize` | NOT the token itself; for re-auth check |
| `advertised_capabilities` | `dict` | Server's capabilities advertisement | Sent at `initialize` reply; cached for reference |
| `negotiated_protocol_version` | `str` | `"2025-11-25"` (the only v1 version) | Per Session 2026-05-13 clarification |

**Lifecycle**:
- `initialize` → MCPSession created, persisted in the per-instance session table (in-memory dict keyed by `mcp_session_id`)
- Each subsequent request → `last_activity_at` updated
- Idle timeout exceeded → session removed; subsequent requests carrying the expired `Mcp-Session-Id` return 404 + JSON-RPC error -32003
- Hard lifetime exceeded → same as idle timeout
- Server restart → all sessions lost (per FR design)
- Cross-instance dispatch → no MCPSession on the target instance; the target instance dispatches the tool call against the bound SACP session id and the bound participant id passed in the proxy hop

**Concurrent-session cap (FR-027)**: Per-instance dict size is checked at `initialize` time; beyond `SACP_MCP_MAX_CONCURRENT_SESSIONS` (default 100), `initialize` returns HTTP 503 + Retry-After.

### ProtocolMessage (in-memory)

The JSON-RPC 2.0 envelope. Existed inline before this spec; this section pins the canonical shape.

**Request envelope**:
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": { "name": "session.create", "arguments": { ... } },
  "id": "<client-supplied opaque id>"
}
```

**Success envelope**:
```json
{
  "jsonrpc": "2.0",
  "result": { ... },
  "id": "<echoes request id>"
}
```

**Error envelope** (per FR-019 + FR-019's data-field requirement):
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {
      "sacp_error_code": "SACP_E_VALIDATION",
      "json_pointer": "/arguments/foo",
      "details": "expected integer, got string"
    }
  },
  "id": "<echoes request id>"
}
```

**Server-initiated notification** (no id):
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/<name>",
  "params": { ... }
}
```

### TransportConnection (per-request)

Request-scoped state for a Streamable HTTP connection. Not stored beyond the request lifetime.

| Field | Type | Notes |
|---|---|---|
| `request_id` | `str` | Opaque per-request id for audit-log correlation |
| `request_started_at` | `datetime` | For V14 stage-timing per-stage measurement |
| `bearer_token_id` | `str` | Hash of the bearer; same as MCPSession's |
| `mcp_session_id` | `bytes` or `None` | Present on every request after `initialize` |
| `rate_limit_bucket_key` | `str` | The key the spec 019 middleware buckets on |

## Phase 3 — In-memory tool registry

### ToolRegistry (in-memory, loaded at startup)

The registry Phase 2's dispatcher reads. Loaded once at orchestrator startup from `src/mcp_protocol/tools/`. Mutation outside startup is NOT supported in v1 (per FR-039).

**Shape**: `Mapping[str, RegistryEntry]` where the key is the tool name (`domain.action` snake_case).

### RegistryEntry

A registry entry wrapping the ToolDefinition + ToolDispatch.

| Field | Type | Notes |
|---|---|---|
| `definition` | `ToolDefinition` | The public-facing tool record returned by `tools/list` |
| `dispatch` | `Callable[[CallerContext, dict], Awaitable[Any]]` | The boundary callable that dispatches to the participant_api router |
| `category` | `str` | One of `session`, `participant`, `proposal`, `review_gate`, `debug_export`, `audit_log`, `detection_events`, `scratch`, `provider`, `admin` |
| `enabled_env_var` | `str` | The `SACP_MCP_TOOL_<CATEGORY>_ENABLED` var that gates this tool |

### ToolDefinition

The public-facing tool record returned by `tools/list`.

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | `domain.action` snake_case (e.g., `session.create`) |
| `description` | `str` | Natural-language hint for the client (English-only in v1) |
| `paramsSchema` | `dict` (JSON Schema) | Validates `tools/call` arguments |
| `returnSchema` | `dict` (JSON Schema) | Validates the dispatch result before serialization |
| `errorContract` | `list[str]` | Enumerated error codes beyond the universal ones |
| `scopeRequirement` | `str` | One of `facilitator`, `participant`, `pending`, `sponsor`, `any` |
| `aiAccessible` | `bool` | Whether AI-side clients can invoke (per FR-063) |
| `idempotencySupported` | `bool` | Write tools only; never `true` for reads |
| `paginationSupported` | `bool` | List-return tools only |
| `v14BudgetMs` | `int` | P95 latency budget for the dispatch path |
| `versionSuffix` | `str` or `None` | `None` for v1 tools; `.v2` etc. on later versions |
| `deprecatedAt` | `datetime` or `None` | Set when the tool enters the deprecation horizon |

### CallerContext

Per-dispatch context the dispatch callable receives.

| Field | Type | Notes |
|---|---|---|
| `participant_id` | `str` | The caller's participant id |
| `session_id` | `str` or `None` | The caller's bound SACP session id |
| `scopes` | `frozenset[str]` | The caller's effective scopes |
| `is_ai_caller` | `bool` | Set by token claim or static-bearer participant.kind |
| `mcp_session_id` | `bytes` or `None` | The MCPSession id; for audit-log correlation |
| `request_id` | `str` | The TransportConnection request id |
| `dispatch_started_at` | `datetime` | For per-stage timing |
| `idempotency_key` | `str` or `None` | If client provided `_idempotency_key`; UUID |

### IdempotencyRecord (DB-resident — uses existing `admin_audit_log`, no new table)

Idempotency-key persistence rides on the existing `admin_audit_log` table. The dispatcher writes the dispatch result into a dedicated `audit.context` field at first call AND queries for the existing audit row on key re-submission. Retention is governed by `SACP_MCP_TOOL_IDEMPOTENCY_RETENTION_HOURS` (default 24, range 1–168).

**Why no new table**: The audit-log is the right place because it's already write-once-per-dispatch AND it already carries the dispatch result. Re-purposing the existing row avoids a new table + migration + schema-mirror update.

### PaginationCursor

Opaque base64-encoded JSON object. Client receives + presents as opaque; only the server decodes.

**Decoded shape**:
```json
{
  "last_id": "<row id sort-key>",
  "sort_key_value": "<sort-column value>",
  "encoded_at": "<iso8601 utc>"
}
```

The `encoded_at` lets the server reject cursors older than a configurable horizon (post-v1 hardening; v1 accepts all valid-shaped cursors).

## Phase 4 — OAuth state schema (NEW alembic migration)

This is the only data-schema migration in the build. It adds five tables under the `oauth_*` prefix.

### `oauth_clients`

Per-MCP-client registration.

| Column | Type | Notes |
|---|---|---|
| `client_id` | `text` PK | Orchestrator-generated opaque value |
| `cimd_url` | `text` | The CIMD URL submitted on first contact |
| `cimd_content` | `jsonb` | The validated CIMD document |
| `redirect_uris` | `text[]` | Allowed redirect URIs from CIMD |
| `allowed_scopes` | `text[]` | Scope vocabulary the client may request |
| `registration_status` | `text` | `pending`, `approved`, `revoked` |
| `registered_at` | `timestamptz` | Server time at registration |
| `revoked_at` | `timestamptz` or `NULL` | Set on operator revocation |

Indexes:
- PK on `client_id`
- UNIQUE on `cimd_url` (one registration per CIMD URL)

### `oauth_authorization_codes`

Short-lived authorization codes; single-use; PKCE-bound.

| Column | Type | Notes |
|---|---|---|
| `code_hash` | `text` PK | SHA-256 of the code (the cleartext is opaque to the server after redemption) |
| `client_id` | `text` FK → `oauth_clients` | |
| `participant_id` | `text` | The subject of the flow |
| `redirect_uri` | `text` | The URI from the authorize request |
| `code_challenge` | `text` | The PKCE challenge (S256 hash) |
| `code_challenge_method` | `text` | Always `S256` per FR-071 |
| `scope` | `text[]` | The requested scopes |
| `issued_at` | `timestamptz` | |
| `expires_at` | `timestamptz` | `issued_at` + `SACP_OAUTH_AUTH_CODE_TTL_SECONDS` (default 60s) |
| `redeemed_at` | `timestamptz` or `NULL` | Set on token-endpoint redemption; codes are single-use |

Indexes:
- PK on `code_hash`
- Compound on `(client_id, issued_at)` for client-scoped audit queries

### `oauth_access_tokens`

In v1, access tokens are JWT-signed (stateless). This table holds a per-JTI revocation pointer for the cases where an access token is revoked AHEAD of its `exp`. Per-dispatch validation reads the per-instance cache (TTL ≤ 30s per FR-094) before falling back to a DB lookup on cache miss.

| Column | Type | Notes |
|---|---|---|
| `jti` | `text` PK | The `jti` claim from the JWT |
| `participant_id` | `text` | The token's `sub` |
| `client_id` | `text` FK → `oauth_clients` | |
| `scope` | `text[]` | The granted scopes |
| `issued_at` | `timestamptz` | The `iat` claim |
| `expires_at` | `timestamptz` | The `exp` claim |
| `revoked_at` | `timestamptz` or `NULL` | Set on revocation |
| `family_id` | `text` FK → `oauth_token_families` | |
| `auth_time` | `timestamptz` | The `auth_time` claim (for step-up freshness checks) |

Indexes:
- PK on `jti`
- Index on `participant_id`
- Index on `family_id`

### `oauth_refresh_tokens`

Opaque refresh tokens; Fernet-encrypted at rest; indexed by hash.

| Column | Type | Notes |
|---|---|---|
| `token_hash` | `text` PK | SHA-256 of the cleartext refresh token |
| `encrypted_token` | `bytea` | Fernet-encrypted cleartext |
| `participant_id` | `text` | The subject |
| `client_id` | `text` FK → `oauth_clients` | |
| `scope` | `text[]` | The granted scopes (same as the original auth code's) |
| `issued_at` | `timestamptz` | |
| `expires_at` | `timestamptz` | `issued_at` + `SACP_OAUTH_REFRESH_TOKEN_TTL_DAYS` |
| `rotated_at` | `timestamptz` or `NULL` | Set when this token is rotated by a refresh request |
| `revoked_at` | `timestamptz` or `NULL` | Set on explicit revocation or family-replay |
| `family_id` | `text` FK → `oauth_token_families` | |
| `parent_token_hash` | `text` or `NULL` FK self-ref → `token_hash` | The previous token in the rotation chain |

Indexes:
- PK on `token_hash`
- Index on `family_id`
- Index on `parent_token_hash`

### `oauth_token_families`

Family tracking for refresh-token replay detection.

| Column | Type | Notes |
|---|---|---|
| `family_id` | `text` PK | Orchestrator-generated at first refresh-token issuance |
| `participant_id` | `text` | |
| `client_id` | `text` FK → `oauth_clients` | |
| `root_token_hash` | `text` | The family-root refresh token's hash |
| `started_at` | `timestamptz` | First refresh-token issuance in this family |
| `revoked_at` | `timestamptz` or `NULL` | Set on family-replay-detected event |

Indexes:
- PK on `family_id`
- Index on `participant_id`

### Migration considerations

- Alembic revision: `022_oauth_state_tables.py` with `revision = "022"`, `down_revision = "021"`. The chain is `... → 019 → 021 → 022`; revision 020 was intentionally skipped in an earlier migration batch. Pre-allocated 2026-05-13.
- `tests/conftest.py` schema mirror updated alongside the migration per `feedback_test_schema_mirror`.
- No data migration for existing data; the tables start empty and populate as OAuth flows complete.

## Phase 5 — Documentation entities (NOT persisted)

### OnboardingBundle (markdown template, not a DB shape)

The four-field markdown structure handed from facilitator to participant. Per FR-102:

```markdown
**Session ID**: `<12-char hex>`
**Participant ID**: `<12-char hex>`
**Bearer Token**: `<32+-char opaque string>`
**Endpoint URL**: `<http://host:port/sse/{session_id}>`

(Masked verification block:)
**Token (masked)**: `…<last 4 chars>`
```

### ParticipantClientConfig (file shape)

The `claude_desktop_config.json` block participants paste into their config. Per FR-119, platform-specific samples included in the docs:

**Windows shape** (per FR-108, FR-109, FR-112):
```json
{
  "mcpServers": {
    "sacp": {
      "command": "C:\\PROGRA~1\\nodejs\\npx.cmd",
      "args": ["mcp-remote", "<endpoint_url>", "--header", "Authorization:Bearer ${SACP_TOKEN}"],
      "env": { "SACP_TOKEN": "<bearer_token>" }
    }
  }
}
```
- Note: 8.3 short-path for `npx.cmd`; no space-after-colon in `--header`; env var holds the token value.

**macOS shape**:
```json
{
  "mcpServers": {
    "sacp": {
      "command": "npx",
      "args": ["mcp-remote", "<endpoint_url>", "--header", "Authorization: Bearer ${SACP_TOKEN}"],
      "env": { "SACP_TOKEN": "<bearer_token>" }
    }
  }
}
```

### TroubleshootingMatrix (markdown table, in `docs/participant-onboarding.md`)

| Symptom | Most-likely root cause | Fix path | Evidence |
|---|---|---|---|
| 401 | Token-in-wrong-field; token expired; auth misconfigured | Confirm bundle's bearer is in env var, not session_id slot; re-issue if expired | (citations per FR-116 + FR-117) |
| 403 | id-vs-token swap (session_id pasted into bearer slot or vice versa) | Bundle review with masked-display block; reissue if confusion persists | 2026-05-12 debug session |
| 404 | Wrong endpoint URL; wrong session_id; orchestrator on different port | Confirm endpoint URL matches `:8750/sse/<session_id>`; confirm session_id length 12 chars | (citations per FR-116) |
| Timeout | Orchestrator unreachable; firewall; proxy interception; Windows Defender first-run stall | Confirm network reachability; check Defender state per FR-111 | 2026-05-12 debug session (Windows Defender stall observed) |
