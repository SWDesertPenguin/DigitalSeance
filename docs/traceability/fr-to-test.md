# FR-to-Test Traceability

Per spec 012 FR-003 / `scripts/check_traceability.py`: every FR/SR marker in
each opt-in spec maps to ≥1 named test path, or carries an `untested` tag with
a non-empty trigger note. Specs absent from this file are skipped by the CI
gate (incremental hand-curation per T021).

Format per row: `| FR-NN | test path(s) | Notes |`

---

## 006-mcp-server

| FR | Test path(s) | Notes |
|---|---|---|
| FR-001 | tests/test_mcp_app.py | FastAPI app creation, router registration |
| FR-002 | tests/test_mcp_auth.py, tests/test_mcp_e2e.py | Bearer auth, session scope, role enforcement |
| FR-003 | tests/test_mcp_e2e.py | Participant lifecycle via API |
| FR-004 | tests/test_mcp_e2e.py | Facilitator-only endpoints reject participant tokens |
| FR-005 | tests/test_mcp_e2e.py | Session-scope binding (cross-session 403) |
| FR-006 | tests/test_rate_limiter.py | Per-participant rate limiting (spec 009) |
| FR-007 | tests/test_mcp_e2e.py | Tool endpoint routing |
| FR-008 | tests/test_mcp_e2e.py | Session creation + participant creation tools |
| FR-009 | tests/test_mcp_e2e.py | Message injection tool |
| FR-010 | tests/test_mcp_e2e.py | History + summary retrieval tools |
| FR-011 | tests/test_mcp_e2e.py | Loop control tools (start_loop, stop_loop) |
| FR-012 | tests/test_mcp_e2e.py | Cross-session scope rejection |
| FR-013 | tests/test_mcp_app.py, tests/test_006_mcp_testability.py | SSE drop-on-full + traceback non-leak parametrized (5 exception types) |
| FR-014 | tests/test_mcp_app.py, tests/test_006_mcp_testability.py | Generic 500 hides traceback; parametrized non-leak matrix |
| FR-015 | tests/test_mcp_app.py, tests/test_006_mcp_testability.py | /docs, /redoc, /openapi.json all gated by SACP_ENABLE_DOCS=1 |
| FR-016 | tests/test_006_mcp_testability.py | CORS octet-corpus (0-255 valid, 256+ rejected); SACP_CORS_ORIGINS override |
| FR-017 | untested | Per-participant SSE cap deferred; trigger: Phase 3 scaling audit |
| FR-018 | untested | Per-tool latency capture deferred per performance checklist; trigger: Phase E ops PR |
| FR-019 | tests/test_006_mcp_testability.py | SSE subscriber cap enforcement; subscriber_count() introspection; cap env var defaults |
| FR-020 | tests/test_006_mcp_testability.py | ContextVar boundary tests validate the propagation primitive; full request-id wiring deferred per performance checklist; trigger: Phase E ops PR |
