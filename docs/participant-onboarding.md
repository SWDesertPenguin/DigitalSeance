# SACP Participant Onboarding

**SACP Phase**: Phase 1 (post-rename; MCP protocol in Phase 2)
**Last Updated**: 2026-05-13
**Tested Against**: Claude Desktop (latest available); mcp-remote (latest npm)

## Overview

SACP (Structured AI Conversation Protocol) is a facilitated multi-participant conversation orchestrator that coordinates turns between human and AI participants in a session. As a participant, you connect to an active SACP session via a client that supports the MCP (Model Context Protocol) bridge pattern — typically Claude Desktop using the `mcp-remote` npm package. This document covers the onboarding flow from the moment you receive your bundle from the facilitator through your first successful connection. It documents the current SACP-native participant API surface (the `/sse/{session_id}` SSE endpoint), with a forward-looking note that Phase 2 will shift MCP clients to the `/mcp` Streamable HTTP endpoint instead.

## Onboarding Bundle Format

The facilitator will send you an onboarding bundle containing exactly four fields in this order:

**Session ID**: `000000000000`
**Participant ID**: `111111111111`
**Bearer Token**: `SACP_DOC_EXAMPLE_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6`
**Endpoint URL**: `http://orchestrator.example:8750/sse/000000000000`

Substitute the placeholder values above with the actual values from your facilitator. The session_id appears in both the "Session ID" field and embedded in the endpoint URL — they must match.

For visual confirmation during side-channel transfer (e.g., when verifying over a voice call or a separate chat thread), the facilitator can share a masked display of the token that shows only the last four characters:

```
Token verification (masked): ****...****P6
```

Compare the last four characters of the masked display against the last four characters of the token you received. If they match, you have the correct token.

## Bearer Token Format

The bearer token is an opaque string of 32 or more characters. It is carried in every HTTP request as the `Authorization` header:

```
Authorization: Bearer SACP_DOC_EXAMPLE_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6
```

The token is the **security primitive** — it identifies who you are and which session you are authorized for. The session_id is the **routing primitive** — it identifies which session's event stream you are subscribing to. Both are required and serve different roles: the orchestrator validates the bearer token against your participant record, and the session_id in the URL routes the request to the correct session. Providing one without the other, or swapping them, produces an authentication or authorization failure.

## Session ID vs Participant ID Distinction

Both the session_id and the participant_id are 12-character hexadecimal strings. Their shape is identical, which makes them easy to confuse when copying values from the bundle.

- The **session_id** is used in the SSE endpoint URL: `http://<host>:8750/sse/<session_id>`
- The **participant_id** is bound to your bearer token at issuance time

If you place the participant_id in the SSE URL, or if the bearer token you were given belongs to a different session, the orchestrator returns **403 Forbidden**. This is the most common cause of 403 errors during onboarding. Use the masked-display block from your bundle to confirm the token's last four characters before troubleshooting further.

## Facilitator Workflow

A facilitator creates a session and issues you a token before sending you the bundle. The steps differ slightly depending on which phase of SACP is deployed.

**Pre-Phase-3 (current state — REST endpoints):**

1. The facilitator calls the session-create REST endpoint to create a new session and records the returned `session_id`.
2. The facilitator calls the participant-create REST endpoint to register you as a participant and receives your bearer token. The token is shown **once** at creation; there is no way to retrieve the plaintext token after this point without rotating it.
3. The facilitator assembles the four-field bundle and delivers it to you via a secure side channel.

**Post-Phase-3 (MCP tool surface):**

1. The facilitator invokes the `session.create` MCP tool, which returns the `session_id`.
2. The facilitator invokes the `participant.create` MCP tool for your participant record and receives the bearer token. The token is shown once on creation; the rotation flow (below) is the recovery path if it is lost.
3. The facilitator assembles and delivers the bundle as before.

## Token Rotation Policy

If your bearer token is lost or compromised, the facilitator invokes the `participant.rotate_my_token` tool (or the REST equivalent in pre-Phase-3 deployments) to issue a new token. The sequence is:

1. Facilitator invokes the rotation endpoint for your participant record.
2. A new token is issued and returned **once** at rotation time. Your old token enters a grace window per spec 002 §FR-007 during which it continues to authenticate; this grace window allows you to update your config before the old token is revoked.
3. The facilitator delivers the new token to you via side channel.
4. You update the `SACP_BEARER_TOKEN` environment variable in your `claude_desktop_config.json` with the new token value. Change only the token value; do not alter the session_id or endpoint URL unless those also changed.
5. Restart Claude Desktop to pick up the new token.

If the old token expires before you have restarted Claude Desktop, you will see a 401 error on reconnect. Obtain the new token from the facilitator and update your config.

## Disconnect and Reconnect

The SACP turn-event stream is **stateless on reconnect**. When your client reconnects after a network drop, laptop sleep, or Claude Desktop restart, the orchestrator does not replay any missed turns — your client re-subscribes to the stream and receives the next turn that arrives after reconnection.

**Catching up on missed turns:** If you were disconnected for a significant stretch and need to see what was said, use the session transcript export surface (per spec 010). The transcript export is read-only and returns the full message history for your session. Ask your facilitator for the transcript export endpoint and your read credentials if this path is not already configured in your client.

**Reconnect-specific failure modes** (distinct from initial-connect failures):

- **401 on reconnect after token rotation**: Your token was rotated while you were disconnected. Obtain the new token from the facilitator, update your config, and restart Claude Desktop.
- **404 on reconnect**: The session was archived while you were disconnected, or the session_id in your config no longer matches a live session.
- **Connection refused on reconnect**: The orchestrator was restarted and is not yet listening, or the host/port changed. Confirm the endpoint URL with your facilitator.

For Windows-specific reconnect issues (Defender re-scanning after sleep), see `docs/participant-onboarding-windows.md`.

## Linux Note

Linux MCP client onboarding is out of scope for v1; no current debug-session data is available, and this path is deferred to a follow-up if Linux MCP clients become a use case.

## Phase 4 OAuth Migration

Phase 4 introduces OAuth 2.1 + PKCE on the MCP endpoint. Static bearer tokens on the participant API routes remain valid; OAuth is layered onto MCP-client connections, not the existing `/sse/{session_id}` participant API surface.

**Master switch:** `SACP_OAUTH_ENABLED` (default `false`). When `false`, the MCP endpoint accepts the legacy bearer-token model and OAuth endpoints are not advertised. When `true`, MCP clients must complete the authorization-code flow described below.

**Endpoints (when `SACP_OAUTH_ENABLED=true`):**

| Path | Method | Purpose |
|---|---|---|
| `/.well-known/oauth-protected-resource` | GET | Discovery metadata per MCP authorization spec; advertises authorization server, token endpoint, supported scopes |
| `/oauth/register-cimd` | POST | Client registration via Client Identity Metadata Document |
| `/authorize` | GET | Authorization code request with PKCE challenge |
| `/token` | POST | Token exchange (authorization code → access + refresh; refresh → rotated pair) |
| `/revoke` | POST | Refresh-token revocation |

**Flow:**

1. Client fetches `/.well-known/oauth-protected-resource` to learn the authorization server URL and supported scopes.
2. Client registers (or re-registers) by POSTing its CIMD to `/oauth/register-cimd`. Registration may be auto-approved or held for facilitator review depending on `SACP_OAUTH_CLIENT_REGISTRATION_MODE`.
3. Client generates a PKCE code verifier + challenge (S256) and redirects the participant to `/authorize?client_id=…&redirect_uri=…&code_challenge=…&code_challenge_method=S256&scope=…&state=…`.
4. Participant authenticates with the orchestrator (existing session-bound token model) and consents to the requested scope set.
5. Authorization server redirects to the client with a short-lived code.
6. Client POSTs the code + PKCE verifier to `/token`, receiving an ES256-signed JWT access token plus a Fernet-encrypted opaque refresh token.
7. Client uses `Authorization: Bearer <access-token>` on MCP requests. On token expiry, client POSTs the refresh token to `/token` (rotating the refresh token in the process — refresh-token reuse triggers a family-wide revocation).
8. Logout / device revocation: client POSTs the refresh token to `/revoke`.

**Scopes:** Bound to the three-role model (facilitator / participant / pending). Scope set granted on the access token determines which MCP tools the client may invoke.

**Token lifetimes:** Access tokens default to 15 minutes (`SACP_OAUTH_ACCESS_TOKEN_TTL_MINUTES`); refresh tokens default to 30 days (`SACP_OAUTH_REFRESH_TOKEN_TTL_DAYS`); authorization codes expire after 60 seconds (`SACP_OAUTH_AUTH_CODE_TTL_SECONDS`).

**Migration from static bearer tokens:** During the grace period set by `SACP_OAUTH_STATIC_TOKEN_GRACE_DAYS` (default 30 days), MCP requests may continue to use the legacy static bearer token. After the grace window, the MCP endpoint requires an OAuth access token. The participant API at `/sse/{session_id}` is unaffected.

**Key rotation:** The ES256 signing key path is `SACP_OAUTH_SIGNING_KEY_PATH`. An optional `SACP_OAUTH_PREVIOUS_SIGNING_KEY_PATH` enables overlap-window verification during rotation — tokens signed by the previous key remain verifiable until they expire.

## Phase 4 local-model deployment

Phase 4 introduces support for participants backed by local inference servers — Ollama and vLLM. The orchestrator treats those endpoints as untrusted upstreams (same SSRF defenses as any other provider) but does NOT probe the listener for auth, enforce TLS, or check the version banner against known-vulnerable releases. Local-model deployment is operator-side responsibility.

Before standing up an Ollama or vLLM listener for a SACP participant, read [`docs/security/local-model-deployment.md`](security/local-model-deployment.md). It covers the default-bind problem (Ollama on `127.0.0.1:11434`, vLLM on `--host`), single-host and multi-host patterns, a Caddy reverse-proxy + Bearer template, hostile-network guidance, and a verification checklist for the listener itself.

## CSRF and Origin Requirements

The current SACP participant API does **not** require `Origin` or `Referer` headers on the `/sse/{session_id}` endpoint. The Web UI's `X-SACP-Request` CSRF middleware is scoped exclusively to Web UI routes and does not apply to participant API routes. If you are scripting a connection directly (e.g., with `curl` or a custom client), you do not need to set these headers. Phase 4 will tighten the authentication surface on the MCP endpoint when OAuth ships; the CSRF posture for the participant API routes is unchanged in the interim.

## Troubleshooting Matrix

| Symptom | Most-likely root cause (first = most common) | Fix path |
|---|---|---|
| 401 Unauthorized | Wrong token in header; expired token; token pasted in session_id slot | Confirm `Authorization: Bearer <token>` header is set; confirm token is the bearer value, not the session_id; re-issue token if expired |
| 403 Forbidden | session_id and bearer token swapped in the bundle (observed 2026-05-12 debug session — both are 12-char hex, easy to mix up); token bound to a different session | Use the masked-display block to confirm the token's last 4 chars match the bundle; check session_id matches the SSE URL |
| 404 Not Found | Wrong endpoint URL; wrong session_id in URL; orchestrator on a different port | Confirm URL is `http://<host>:8750/sse/<12-char-session-id>`; confirm session exists and has not been archived |
| Connection timeout / no response | Orchestrator unreachable (network, firewall); Windows Defender first-run scan stalling the `mcp-remote` process (observed 2026-05-12 debug session — can stall several minutes on first invocation); proxy intercepting the connection | Confirm network reachability; on Windows, check if Defender is scanning — see the Windows onboarding doc; check for proxy env vars |

## Cross-References to Phases 1–4

The SACP MCP build is a five-phase sequence. The cross-references below explain what each phase contributes and how it affects this document.

**Phase 1 — Codebase Restructure**: The module previously called `src/mcp_server/` is renamed to `src/participant_api/` as part of this phase. The `/sse/{session_id}` endpoint you connect to lives under `src/participant_api/` after the rename. The rename is a behavior-preserving refactor; nothing about the participant-facing behavior changes.

**Phase 2 — MCP Protocol over Streamable HTTP**: Phase 2 populates `src/mcp_protocol/` with a standards-compliant MCP transport layer. Once Phase 2 ships, MCP clients (Claude Desktop via `mcp-remote`, claude code, Cursor) connect to `http://<host>:8750/mcp` using the Streamable HTTP transport instead of the SSE endpoint at `/sse/{session_id}`. This document will be updated at Phase 2 ship time to document the new endpoint and note the `/sse/` surface as the legacy path.

**Phase 3 — SACP-to-MCP Tool Mapping**: Phase 3 defines the tool registry that makes SACP operations available as callable tools within Claude Desktop and other MCP clients. The `session.create`, `participant.create`, and `participant.rotate_my_token` tool calls referenced in the Facilitator Workflow and Token Rotation Policy sections above are Phase 3 deliverables.

**Phase 4 — OAuth 2.1 + PKCE**: Phase 4 replaces the static bearer token with an OAuth 2.1 Authorization Code flow with PKCE on the MCP endpoint. The Phase 4 OAuth Migration section above is reserved for the updated onboarding flow when Phase 4 ships. Static bearer tokens on the participant API routes remain valid after Phase 4.
