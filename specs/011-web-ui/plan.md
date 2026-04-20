# Implementation Plan: Phase 2 Web UI

**Branch**: `011-web-ui` | **Date**: 2026-04-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/011-web-ui/spec.md`

## Summary

A browser-based operational interface for SACP sessions that replaces Swagger-driven usage. Ships as a second FastAPI app on port 8751 that reuses the Phase 1 services, database pool, and token auth. The frontend is a single-file React SPA loaded from CDN (no build toolchain) rendering a three-column layout: participant list + session controls (left), transcript + injection input (center), dashboard panels — budget, convergence, summary, review gate, proposals (right). A per-session WebSocket (`/ws/{session_id}`) streams turn completions, participant updates, convergence scores, and review-gate drafts; client mutations go through the existing REST endpoints. Internal phasing: 2a core (auth, transcript, injection, WS, participant health), 2b dashboard (budget, convergence, summary, admin panel), 2c workflows (review gate, proposals, export).

## Technical Context

**Language/Version**: Python 3.11+ (backend, reuses Phase 1), JSX via Babel Standalone (frontend, browser-interpreted)
**Primary Dependencies**:
- Backend: FastAPI, uvicorn, asyncpg (all already pinned in pyproject.toml)
- Frontend (CDN, SRI-pinned): React 18, ReactDOM 18, marked (markdown parser), DOMPurify (sanitizer)
**Storage**: Reuses Phase 1 Postgres 16 via the existing repository layer — no new tables
**Testing**: pytest for backend routes and WS handshake; Playwright for end-to-end UI smoke tests; manual checklist in `quickstart.md` for CSP/XSS vectors
**Target Platform**: Linux server (Docker Compose, same container or sidecar — decided in research.md)
**Project Type**: web (backend + SPA frontend bundled as static asset)
**Performance Goals**:
- Turn-to-render latency ≤ 2s from `message` WS event receipt (SC-002)
- WebSocket reconnect within 30s of network drop with full `state_snapshot` resync (SC-003)
- ≤ 200 message DOM nodes before virtualization is considered (spec Assumption)
**Constraints**:
- Strict CSP with no `unsafe-inline`, no `data:` images, no wildcard CORS
- HttpOnly bearer-token cookie or React ref only — never `localStorage` / `sessionStorage` (FR-003)
- Response size cap on all WS payloads (mirrors Phase 1 response-size enforcement)
- No build toolchain — the feature ships as one HTML + one JSX file loadable from a browser
**Scale/Scope**:
- 2–10 participants per session (same as Phase 1)
- ~25 WebSocket events, ~25 REST endpoints (all already exist in Phase 1)
- Target initial LOC: ≤ 2000 JSX lines before module split (spec FR-002)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| V1 Sovereignty | PASS | UI never displays API keys (SR-007) or private prompt contents. Token held in HttpOnly cookie / React ref only. |
| V2 No cross-phase leakage | PASS | OAuth/PKCE, branching UI, sub-sessions, artifact store — explicitly out of scope per spec §"Out of Scope". |
| V3 Security hierarchy | PASS | SR-001 through SR-008 cover XSS, CSRF, CORS, CSP, cache, clickjacking. No stylistic trade-off weakens any. |
| V4 Facilitator bounded | PASS | UI mirrors Phase 1 facilitator capabilities; no new admin powers beyond what Phase 1 already grants. |
| V5 Transparency | PASS | WS events expose routing decisions, convergence scores, circuit-breaker state. Nothing hidden from the participant. |
| V6 Graceful degradation | PASS | WS auto-reconnect with exponential backoff; disconnected UI falls back to REST polling on demand. |
| V7 Coding standards | PASS | 25/5 lint enforced on backend Python. Frontend JSX under `frontend/` with equivalent informal caps. |
| V8 Data security | PASS | Budget data redacted per policy (FR-010), tokens never persisted to storage, CORS own-origin only. |
| V9 Log integrity | PASS | UI reads audit log only (`GET /tools/debug/export`). No new log writes from the UI layer. |
| V10 AI security pipeline | PASS | FR-006 + SR-005 require DOMPurify + markdown security overrides; matches Phase 1 exfiltration defenses. |
| V11 Supply chain | PASS | All CDN assets loaded with SRI hashes. No new Python deps beyond what's already pinned. |
| V12 Topology compatibility | PASS | UI serves topologies 1–6 (orchestrator-driven). Topology 7 (MCP-to-MCP) flagged in spec as Phase 3. |
| V13 Use case coverage | PASS | Spec §"Topology and Use Case Coverage" references US1 / US2 / US4 / US5. |

No violations. Complexity Tracking section left empty.

## Project Structure

### Documentation (this feature)

```text
specs/011-web-ui/
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 — decisions + rationale
├── data-model.md        # Phase 1 — WS event shapes + client state
├── quickstart.md        # Phase 1 — dev loop + manual XSS checklist
├── contracts/
│   ├── websocket-events.md   # Server → client push events
│   └── rest-endpoints.md     # REST surface consumed by UI (Phase 1 inventory)
├── spec.md              # Feature spec (already written)
└── tasks.md             # Phase 2 — /speckit.tasks output (NOT generated here)
```

### Source Code (repository root)

```text
src/
├── mcp_server/              # Phase 1 FastAPI app on port 8750 (unchanged)
│   └── tools/               # 25 existing endpoints — reused by UI
├── web_ui/                  # NEW — Phase 2 FastAPI app on port 8751
│   ├── __init__.py
│   ├── app.py               # create_web_app() factory, CSP/security headers
│   ├── auth.py              # Token-cookie handshake, session→participant lookup
│   ├── websocket.py         # /ws/{session_id} endpoint, subscriber registry
│   └── events.py            # Event shapes + broadcast plumbing (reuses ConnectionManager)
├── orchestrator/            # Phase 1 — unchanged
├── repositories/            # Phase 1 — unchanged
└── ...

frontend/                    # NEW — browser-delivered assets
├── index.html               # Single-file React app entrypoint, CDN script tags with SRI
├── app.jsx                  # Root component + router
├── components/              # Split when index.html exceeds ~2000 lines
│   ├── SessionView.jsx
│   ├── Transcript.jsx
│   ├── ParticipantList.jsx
│   ├── BudgetPanel.jsx
│   ├── ConvergencePanel.jsx
│   ├── SummaryPanel.jsx
│   ├── ReviewGateQueue.jsx
│   ├── AdminPanel.jsx
│   └── AuthGate.jsx
└── style.css                # Dark-theme defaults

tests/
├── test_web_ui_app.py           # FastAPI handshake + security-header contract tests
├── test_web_ui_websocket.py     # WS event broadcast + reconnect semantics
└── e2e/                         # Playwright smoke — login, send, receive, reconnect
    └── test_session_flow.py
```

**Structure Decision**: Two-app backend (Phase 1 MCP server on 8750, Phase 2 Web UI on 8751) + one static SPA (`frontend/`). The UI server is a thin FastAPI app that reuses `request.app.state.{session_repo, participant_repo, conversation_loop, connection_manager, ...}` from the Phase 1 factory via a shared `create_app()` pattern. Separating the apps keeps the Phase 1 MCP contract unchanged while letting the UI serve static assets and a WebSocket endpoint independently. The `frontend/` directory is served by the web UI app as static files under `/`; `index.html` is the fall-through for SPA routing.

## Complexity Tracking

*No constitutional violations. This section is empty by design.*
