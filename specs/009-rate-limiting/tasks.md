# Tasks: Rate Limiting

> **Status: SHIPPED 2026-04-20 as part of Phase 1.** Task list is historical; outstanding checkboxes were not all carried out as written (scope evolved through PR review).

**Input**: Design documents from `/specs/009-rate-limiting/`

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Add rate_limiter placeholder to `src/mcp_server/`

---

## Phase 2: US1 — Per-Participant Rate Limiting (P1)

- [X] T002 [US1] Implement `src/mcp_server/rate_limiter.py` — sliding window counter per participant, 60 req/min default
- [X] T003 [US1] Add FastAPI middleware to enforce limits on all /tools/* endpoints
- [X] T004 [US1] Return 429 with Retry-After header when limit exceeded
- [X] T005 [US1] Add per-IP global cap as DoS backstop
- [X] T006 [US1] Write `tests/test_rate_limiter.py` — test within-limit succeeds, over-limit returns 429, window resets, per-participant isolation

---

## Phase 3: Polish

- [X] T007 [P] Attach RateLimiter to app.state in `src/mcp_server/app.py`
- [X] T008 Run full test suite to verify no regressions

---

## Dependencies

- Setup → US1 (straightforward single-story feature)
- MVP: US1 complete = feature complete

## Notes

- 8 tasks
- No new dependencies (in-memory counters only)
- Defaults: 60 req/min per participant, 300 req/min per IP
- All tasks COMPLETED in PR #45-47
