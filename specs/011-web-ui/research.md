# Research: Phase 2 Web UI

**Branch**: `011-web-ui` | **Date**: 2026-04-20

## Purpose

Resolve open questions implied by `spec.md` and `plan.md` before design work begins.

---

## D1 — Frontend delivery: single-file SPA vs. small multi-file

**Decision**: Start as single-file `index.html` + `app.jsx`. Split into `components/*.jsx` once the root file exceeds ~2000 lines or when Phase 2b lands the dashboard (whichever comes first).

**Rationale**: Matches FR-002 ("Single-file React JSX, CDN-loaded, no build toolchain. Split to modules if exceeding ~2000 lines."). Single-file ships Phase 2a faster, reviews easier, avoids bundler complexity. Splitting is cheap once the seams are clear from the running UI.

**Alternatives considered**:
- **Vite + TypeScript build**: rejected — spec explicitly forbids a build toolchain in Phase 2.
- **Component-per-file from day one**: rejected — premature split before the layout shakes out; extra browser round-trips without HTTP/2 push.

---

## D2 — WebSocket transport choice

**Decision**: Native FastAPI `WebSocket` at `/ws/{session_id}` on port 8751. Server push only; client sends `pong` (liveness) and `subscribe` (filter) frames. Messages are JSON, one event per frame.

**Rationale**: SACP Phase 1 already has a `ConnectionManager` (`src/mcp_server/connection_manager.py`) used for SSE turn broadcasts. Reusing the same broadcast contract via a second subscriber interface keeps the Phase 1 loop code untouched while letting the Web UI receive the same turn events. FastAPI WebSocket is well-supported, works under the existing uvicorn process, and has no runtime dependency.

**Alternatives considered**:
- **Server-Sent Events (SSE) only**: rejected — SSE is one-way; we don't need two-way *application* traffic, but we do need a `pong` heartbeat to detect stale connections through NAT timeouts. WebSocket handles this natively with `ping/pong` frames.
- **Socket.IO / socketio**: rejected — added dependency, features we don't need (fallbacks, rooms), weaker CSP story.

---

## D3 — Backend topology: one process, two apps

**Decision**: A single `uvicorn` process serves two FastAPI apps on different ports via a shared `create_app()` factory. The Phase 1 MCP app keeps port 8750 unchanged. A new `create_web_app()` factory in `src/web_ui/app.py` runs on port 8751 and is mounted or launched alongside the MCP app in the Docker entrypoint.

**Rationale**: Phase 1 invariants (port 8750, 25 endpoints, rate limiter middleware) must not change. A separate app lets the Web UI have its own CSP/security headers, its own CORS policy (own-origin only), its own middleware chain, and a clean `/ws/*` route without polluting the MCP namespace. The shared state (`request.app.state.pool`, `session_repo`, `participant_repo`, `conversation_loop`, etc.) is passed by reference so no duplicate resources are allocated.

**Alternatives considered**:
- **Mount the Web UI under `/ui` on the existing MCP app**: rejected — the MCP app's CORS is wildcard-relaxed for participant clients; the Web UI needs strict same-origin. Mixing them forces exceptions.
- **Separate container**: rejected for Phase 2 — operationally heavier, requires service discovery and another port mapping for no payoff.

---

## D4 — Auth flow

**Decision**: User POSTs `/login` with bearer token in the request body. Server validates via Phase 1 `auth_service.validate_token(token, ip)` (reusing the same function the MCP app uses) and sets an HttpOnly, Secure, SameSite=Strict cookie bound to the `(participant_id, session_id)`. WebSocket upgrade reads the cookie; REST calls from the UI include a `X-SACP-Request: 1` header for CSRF.

**Rationale**: Keeps bearer-token material out of JS memory entirely (FR-003). Same-origin cookie eliminates CSRF-via-cookie risk when combined with the custom header (SR-006). Reusing `auth_service.validate_token` means no auth code duplication.

**Alternatives considered**:
- **Token-in-header per request**: rejected — requires storing the token somewhere JS can read, violating FR-003.
- **OAuth 2.1 / PKCE**: explicitly Phase 3 per constitution §10.

---

## D5 — State snapshot on WebSocket connect

**Decision**: On connect, the server sends a single `state_snapshot` event containing: session row, participant list with health fields, last 50 messages (with summaries dereferenced), pending review-gate drafts, open proposals, latest summary row, recent convergence scores. Subsequent updates are delta events.

**Rationale**: Satisfies FR-005 and US3 AC2 ("on reconnect, receives full state_snapshot to resync"). 50-message initial cap matches the spec's ~200-message DOM cap but leaves headroom for the user to scroll-load more via REST.

**Alternatives considered**:
- **Incremental events from turn 0**: rejected — slow first render on long sessions, lots of round-trips.
- **Full transcript in the snapshot**: rejected — payload bloat, breaches response-size caps on multi-hundred-turn sessions.

---

## D6 — Frontend testing strategy

**Decision**: Two layers.
1. **Backend tests** (pytest): cover the FastAPI app factory, security-header middleware, WS handshake, cookie auth, and event broadcast plumbing.
2. **End-to-end smoke** (Playwright, Python driver): one test per user story that logs in, exercises the flow, asserts the expected DOM/network outcomes. Lives in `tests/e2e/`.
3. **No Jest / React Testing Library**: the UI is thin, component logic minimal. If interactive complexity grows, revisit in Phase 2c.

**Rationale**: Playwright runs against the real bundle so it catches CSP regressions and CDN integrity failures. Jest would require a Node toolchain we're deliberately avoiding.

**Alternatives considered**:
- **Jest + jsdom**: rejected — adds Node dependency, doesn't catch CSP or CDN integrity issues.
- **Manual testing only**: rejected — won't detect regressions once Phase 2c lands.

---

## D7 — CDN pinning and SRI

**Decision**: Every `<script>` and `<link>` tag loading an external asset MUST include an `integrity="sha384-..."` attribute computed from the pinned version. React 18.3.1, ReactDOM 18.3.1, Babel Standalone 7.25.x, marked 15.x, DOMPurify 3.x — all pinned; SRI hashes captured in `contracts/frontend-assets.md` (generated during Phase 2a task work).

**Rationale**: V11 supply chain — frontend assets are just as critical as Python dependencies. CDN compromise without SRI would execute arbitrary code in every user's browser. SRI makes the browser refuse to run a modified payload.

**Alternatives considered**:
- **Self-host all assets**: deferred — means shipping ~300KB of vendor JS in the repo, bumping every React security patch. SRI-pinned CDN is the pragmatic middle ground.

---

## D8 — Event schema versioning

**Decision**: Every WebSocket event includes a `"v": 1` field. Server refuses to send events to clients that don't handshake the version on connect; client refuses to act on unknown `v` values. Version bumps require a plan addendum.

**Rationale**: The UI will evolve through Phase 2a → 2b → 2c and into Phase 3 (branching). Locking event shapes behind a version guard lets us deploy server and client out of lockstep without cryptic runtime errors.

**Alternatives considered**:
- **No versioning (assume lockstep)**: rejected — deployment reality is that WebUI and MCP server may ship in different PRs.

---

## Open items (none)

All NEEDS CLARIFICATION items in `plan.md` were resolvable from the spec + Phase 1 implementation. No items carried forward into `tasks.md` as blockers.
