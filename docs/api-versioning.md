# API Versioning and Deprecation Policy

**Status**: Phase 2 decision record — no formal versioning in Phase 1/2; policy defined here for
Phase 3 readiness. Per constitution §14 and spec 012 Phase G audit.

---

## Current state (Phase 1/2)

SACP exposes two API surfaces with no formal version identifiers today:

| Surface | Transport | Base path | Versioning |
|---|---|---|---|
| MCP tool API | HTTP POST + SSE | `/tools/**`, `/sse/**` | None |
| Web UI REST | HTTP | `/login`, `/logout`, `/me`, `/api/mcp/**` | None |
| Web UI WebSocket | WS | `/ws/{session_id}` | None |
| Health / meta | HTTP | `/healthz`, `/csp-report` | None |

No `API-Version` header, no URL path prefix (`/v1/`), no `Accept: application/vnd.*` negotiation
exists. This is intentional for Phase 1/2: the system is single-operator, single-instance, and
the CLI + Web UI are first-party clients whose upgrade is coordinated with the server.

---

## MCP protocol-version drift

SACP's MCP tool API is a **bespoke REST + SSE pattern**, not an implementation of the
[MCP protocol SDK](https://github.com/modelcontextprotocol). Per spec 006 Assumptions (2026-05-01):

> "Phase 1 uses simple SSE streaming, not the full MCP protocol SDK. MCP protocol compliance
> is a future enhancement."

The divergence is deliberate: the MCP protocol SDK's schema and negotiation overhead was not
warranted for Phase 1's single-tenant, trusted-network deployment. The divergence becomes
load-bearing in Phase 3 when third-party MCP clients may connect.

**Trigger for alignment work**: any Phase 3 feature that exposes the MCP API to a client not
controlled by the operator (external participant, third-party dashboard, SDK-based integration).

---

## Phase 3 versioning strategy (proposed)

When Phase 3 introduces the first breaking change, the preferred approach is:

1. **URL-prefix versioning** (`/v2/tools/**`) — simple, cacheable, explicit in logs.
   Preferred over header-based negotiation for tool APIs because tool clients (LiteLLM
   dispatch, Web UI proxy) have predictable upgrade paths.

2. **Sunset header** — responses from the v1 surface include
   `Sunset: <ISO-date>` and `Deprecation: true` for one full release cycle before removal,
   giving operators time to upgrade connected clients.

3. **Version discovery** — `/api/version` endpoint returning `{"api_version": "2", "min_supported": "1"}`.
   Clients that need negotiation query this before connecting. Phase 3 trigger: when a
   third-party client appears that cannot be force-upgraded.

No action required in Phase 2. Record the strategy now so Phase 3 design does not reopen
the decision.

---

## Breaking-change definition

A change is **breaking** if it causes a correctly-implemented Phase 2 client to fail or produce
wrong results without modification:

- Removing a tool endpoint or WS message type
- Renaming a required request field or changing its type
- Changing a response field that clients are documented to consume
- Changing a documented HTTP status code (e.g., 401 → 403 for a given error)
- Removing a documented WS close code

Non-breaking changes (additive only):
- Adding optional request fields with documented defaults
- Adding new response fields
- Adding new endpoints or WS event types
- Tightening validation that would only fail previously-invalid inputs

---

## Operator compatibility window

Phase 2→3 transition policy (proposed, not yet ratified):

- The Phase 2 API surface stays accessible for **one full Phase** (i.e., until Phase 4) after
  Phase 3 ships any breaking change.
- Operators receive a `Sunset` header on affected endpoints from the day Phase 3 ships.
- The Phase 2 Web UI (`app.jsx`) is cached by browsers; operators MUST set
  `Cache-Control: no-store` (already the default, see spec 011 SR-005) to force reload.
- A single-page migration guide ships alongside any Phase 3 breaking change.

---

## Feature-flag patterns (current de-facto versioning)

Env vars gate features that are off by default. This is the current Phase 1/2 versioning
mechanism for optional behaviour:

| Env var | Default | Feature it gates |
|---|---|---|
| `SACP_ENABLE_DOCS` | `0` | Swagger UI (`/docs`, `/redoc`, `/openapi.json`) |
| `SACP_TRUST_PROXY` | `0` | X-Forwarded-For honour in IP binding |
| `SACP_WEB_UI_INSECURE_COOKIES` | `0` | HTTP (non-TLS) cookie deployment |
| `SACP_MAX_SUBSCRIBERS_PER_SESSION` | `64` | Per-session SSE subscriber cap |

All vars are documented in `docs/env-vars.md` with types, ranges, and V16 startup validation.

For Phase 3 feature flags: maintain the same env-var pattern. A formal feature-flag registry
is deferred; the `docs/env-vars.md` catalog is the registry.

---

## Client SDK compatibility

**Phase 1/2**: No public client SDK. First-party clients only:
- CLI (`sacp-admin` tool, operator-side)
- Web UI (`frontend/app.jsx`, browser SPA)

Both are upgraded in lockstep with the server; no compatibility window is required within
Phase 2.

**Phase 3 target**: if an MCP client SDK ships, it must declare its minimum supported
server API version. The server's `/api/version` endpoint (see above) enables negotiation.

---

## API contract testing

**Current state**: Ad-hoc. The Web UI talks to the MCP API exclusively via the same-origin
proxy (`/api/mcp/**`). Integration is verified end-to-end by `tests/test_loop_integration.py`
and `tests/test_web_ui_proxy.py`, not by explicit API contract assertions.

**Phase 3 target**:
- OpenAPI schema (`/openapi.json`) exported and committed to `contracts/mcp-api.yaml`.
- `pytest-schemathesis` or equivalent runs contract fuzz tests in CI against the schema.
- Web UI Playwright e2e (Phase F) implicitly validates the contract from the client side.

**Trigger**: any Phase 3 PR that adds, removes, or renames a tool endpoint.

---

## Rollback strategy

SACP has no hot-rollback mechanism today (single-instance, forward-only alembic migrations).
Per ADR 0001 and Phase 1/2 assumptions, the rollback strategy is:

1. Restore the previous Docker image tag.
2. Restore the database from the last backup taken before the breaking migration (see
   `docs/env-vars.md` `SACP_AUDIT_RETENTION_DAYS` and 001 ops items for backup policy).
3. Re-run any data-only migration that is idempotent.

No in-place version downgrade is supported. Destructive schema migrations (DROP COLUMN,
DROP TABLE) require explicit operator approval gate per the 001 migration-safety audit items
(Phase F).
