# Tasks: Debug Export

**Input**: Design documents from `/specs/010-debug-export/`

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Create `src/mcp_server/tools/debug.py` with `/tools/debug` router prefix

---

## Phase 2: US1 — Single-Call Troubleshooting Dump (P1)

- [X] T002 [US1] Implement `GET /tools/debug/export` endpoint with facilitator role check + session-id match
- [X] T003 [US1] Implement `_serialize` / `_jsonify` helpers for dataclass + datetime + bytes coercion
- [X] T004 [US1] Strip `api_key_encrypted`, `auth_token_hash`, `bound_ip` from participants via `_scrub`
- [X] T005 [US1] Fetch routing_log, usage_log, convergence_log, admin_audit_log for the session
- [X] T006 [US1] Add `_config_snapshot` with fixed `SACP_*` allowlist (no secrets)
- [X] T007 [US1] Register `debug_router` in `src/mcp_server/app.py`
- [X] T008 [US1] Add e2e tests in `tests/test_mcp_e2e.py` — facilitator 200, participant 403, scrubbing, config_snapshot present

---

## Phase 3: Polish

- [X] T009 Run full test suite to verify no regressions

---
