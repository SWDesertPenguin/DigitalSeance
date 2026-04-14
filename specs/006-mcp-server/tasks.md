# Tasks: MCP Server

**Input**: Design documents from `/specs/006-mcp-server/`

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Create `src/mcp_server/` and `src/mcp_server/tools/` directories with `__init__.py`
- [X] T002 Implement `src/mcp_server/middleware.py` — auth dependency extracting bearer token, validating via AuthService, injecting participant into request state

---

## Phase 2: US1 — SSE Connection (P1)

- [X] T003 [US1] Implement `src/mcp_server/app.py` — FastAPI app with lifespan (pool creation, model loading), SSE endpoint at /sse/{session_id} streaming turn results
- [X] T004 [US1] Write `tests/test_mcp_auth.py` — test valid token accepted; test invalid token returns 401; test missing token returns 401

---

## Phase 3: US2+3 — Injection + Session Lifecycle (P1)

- [X] T005 [US2] Implement `src/mcp_server/tools/participant.py` — inject_message endpoint (enqueues to interrupt queue via InterruptRepository)
- [X] T006 [US3] Implement `src/mcp_server/tools/session.py` — create_session, pause_session, resume_session, archive_session endpoints using SessionRepository + AuthService

---

## Phase 4: US4 — Facilitator Tools (P2)

- [X] T007 [US4] Implement `src/mcp_server/tools/facilitator.py` — create_invite, approve_participant, reject_participant, remove_participant, revoke_token, transfer_facilitator endpoints (all gated by facilitator role via AuthService)

---

## Phase 5: US5+6 — Self-Service + Loop Control (P2)

- [X] T008 [US5] Extend `src/mcp_server/tools/participant.py` — get_status, get_history, get_summary, set_routing_preference, rotate_token endpoints
- [X] T009 [US6] Extend `src/mcp_server/tools/session.py` — start_loop, stop_loop endpoints (facilitator only, manages ConversationLoop as asyncio task)

---

## Phase 6: US7 — Export (P3)

- [X] T010 [US7] Extend `src/mcp_server/tools/session.py` — export_markdown, export_json endpoints (any authenticated participant)

---

## Phase 7: Tests + Polish

- [X] T011 Write `tests/test_mcp_tools.py` — test inject_message enqueues; test session lifecycle transitions; test facilitator tools gated; test self-service returns data; test loop start/stop; test export formats
- [X] T012 Write `tests/test_mcp_app.py` — test app starts on configured port; test SSE endpoint streams events; test unauthenticated requests rejected
- [X] T013 Update `src/mcp_server/__init__.py` — export create_app function
- [X] T014 Run full test suite (features 001-006) and verify no regressions

---

## Dependencies

- Setup → US1 → US2+3 → US4 → US5+6 → US7 → Tests
- MVP: US1 + US2 + US3 (connect, inject, create session)

## Notes

- 14 tasks
- No new dependencies — FastAPI + uvicorn already installed
- All tool endpoints are thin wrappers over existing services
- Auth middleware is a FastAPI dependency injection pattern
