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

---

## 011-web-ui

| FR/SR | Test path(s) | Notes |
|---|---|---|
| FR-001 | tests/test_web_ui_app.py | FastAPI app factory; /healthz without DB |
| FR-002 | tests/test_web_ui_app.py | frontend/ static files served at / |
| FR-003 | tests/test_web_ui_websocket.py | WS auth close codes (missing cookie, unknown sid, wrong session) |
| FR-004 | tests/test_web_ui_websocket.py | WS Origin validation; missing/bad origin closes 4403 |
| FR-005 | untested | state_snapshot delivery on WS connect needs full WS auth; trigger: Phase F Playwright or integration |
| FR-006 | tests/test_011_testability.py | SR-010 pending snapshot includes human participants only |
| FR-007 | untested | WS ping/keepalive; trigger: Phase F Playwright or integration |
| FR-008 | untested | WS broadcast fan-out to >1 subscriber; trigger: Phase F or integration |
| FR-009 | tests/test_web_ui_app.py, tests/test_web_ui_proxy.py | /login + MCP proxy; /logout clears cookie |
| FR-010 | untested | Session-bound token (cookie→bearer); trigger: integration test Phase F |
| FR-011 | untested | Convergence sparkline in snapshot; trigger: Phase F |
| FR-012 | tests/test_web_ui_auth.py | Cookie opaque sid; bearer not in cookie (H-02/M-08) |
| FR-013 | tests/test_web_ui_app.py | CORS strict default; SACP_WEB_UI_ALLOWED_ORIGINS override |
| FR-014 | untested | Auto-reconnect backoff is client-side JS timer; trigger: Phase F Playwright |
| FR-015 | tests/test_web_ui_app.py | SACP_ENABLE_DOCS gate not applicable to Web UI (MCP-server feature); healthz always on |
| FR-016 | tests/test_web_ui_proxy.py | Same-origin /api/mcp/* proxy injects bearer server-side |
| FR-017 | tests/test_web_ui_auth.py | SACP_WEB_UI_COOKIE_KEY independent of SACP_ENCRYPTION_KEY (M-02) |
| FR-018 | tests/test_web_ui_auth.py | IP binding mismatch returns generic 403, no IP echo (H-01) |
| FR-019 | untested | CSP violation report forwarding to aggregator is Phase 3 deferred |
| FR-020 | untested | Invite-redeem flow; trigger: fix/002-compliance Phase D |
| SR-001 | tests/test_web_ui_app.py, tests/test_011_testability.py | Security headers present; CSP report-uri; per-directive coverage (14 fragments) |
| SR-001a | untested | WS frame cap (256KB); WS layer max_size not yet wired; trigger: Phase E ops |
| SR-002 | tests/test_web_ui_app.py | Strict-Transport-Security header present |
| SR-003 | tests/test_web_ui_app.py | X-Frame-Options: DENY present |
| SR-004 | tests/test_web_ui_websocket.py | WS Origin header validation; missing/bad origin → 4403 |
| SR-005 | tests/test_web_ui_app.py | Cache-Control: no-store present |
| SR-006 | tests/test_web_ui_app.py | CSRF: POST without X-SACP-Request → 403; with header → passes |
| SR-007 | untested | No API keys/system prompts serialised by SPA is behavioural; trigger: Phase F Playwright snapshot check |
| SR-008 | tests/test_web_ui_app.py | Permissions-Policy header present |
| SR-009 | untested | Forbidden link schemes require browser rendering; trigger: Phase F Playwright |
| SR-010 | tests/test_011_testability.py | Pending snapshot filters to humans only; empty messages/drafts/proposals |
| SR-011 | tests/test_011_testability.py | _participant_dict excludes api_key_encrypted, auth_token_hash, auth_token_lookup, token_expires_at, bound_ip |
| SR-012 | untested | Malformed-frame discard + connection-survives needs full WS auth; trigger: Phase F integration |

---

## 002-participant-auth

| FR | Test path(s) | Notes |
|---|---|---|
| FR-001 | tests/test_auth_service.py | Valid token authenticates; invalid + missing tokens rejected |
| FR-002 | tests/test_002_testability.py | Expired token raises TokenExpiredError; valid-before-expiry accepted |
| FR-003 | tests/test_auth_service.py | Missing + empty token raises AuthRequiredError |
| FR-004 | untested | Plaintext-in-log prevention is covered by 007 ScrubFilter; dedicated token-pattern log test deferred to Phase E |
| FR-005 | tests/test_approval.py | Approve changes role to participant + sets approved_at |
| FR-006 | tests/test_approval.py | Reject removes participant record |
| FR-007 | untested | auto_approve exercised in fixtures; dedicated auto-approve flow test deferred to Phase F |
| FR-008 | tests/test_auth_service.py, tests/test_auth_token_lookup.py | Self-rotate returns new token; old token rejected; HMAC lookup column populated |
| FR-009 | tests/test_auth_service.py | Facilitator revoke invalidates token |
| FR-010 | tests/test_approval.py, tests/test_002_testability.py | Non-facilitator approve rejected; non-facilitator transfer rejected |
| FR-011 | tests/test_002_testability.py | Transfer swaps roles atomically; session.facilitator_id updated; pending target rejected |
| FR-012 | tests/test_002_testability.py | token_expires_at set to future after rotation |
| FR-013 | tests/test_002_testability.py | Rotation resets expiry timestamp |
| FR-014 | tests/test_002_testability.py, tests/test_approval.py | All five facilitator actions logged (approve, reject, remove, revoke, transfer) |
| FR-015 | untested | Pending endpoint guard (inject_message + add_ai); trigger: endpoint matrix Phase B fix/011-testability |
| FR-016 | tests/test_002_testability.py | First auth binds bound_ip; subsequent same-IP accepted |
| FR-017 | tests/test_002_testability.py | Mismatched IP raises IPBindingMismatchError |
| FR-018 | tests/test_002_testability.py | Token rotation clears bound_ip; new token re-binds to new IP |
| FR-019 | tests/test_approval.py | Self-removal rejected |
| FR-020 | untested | Pending scope Phase 1 single default; trigger: per-session scope override Phase 3 |
| FR-021 | untested | Endpoint-boundary pending guard; trigger: endpoint matrix Phase B fix/011-testability |
| FR-022 | untested | HTTPBearer() enforces Authorization header form; malformed-header matrix deferred to Phase B |
| FR-023 | tests/test_002_testability.py | TRUST_PROXY=0 uses direct client.host; TRUST_PROXY=1 uses rightmost XFF |
| FR-024 | tests/test_002_testability.py | Documented absence: 5 wrong tokens do not lock out the valid one (brute-force OOS Phase 1) |
| FR-A1 | tests/test_002_testability.py | Rotated token matches URL-safe base64 pattern; length >= 40 chars |

---

## 001-core-data-model

| FR | Test path(s) | Notes |
|---|---|---|
| FR-001 | tests/test_session_crud.py | Session creation + main branch atomicity |
| FR-002 | tests/test_session_crud.py | Facilitator participant created on session create |
| FR-003 | tests/test_participant.py | Participant record persistence |
| FR-004 | tests/test_participant.py | API key encrypted at rest; decrypt_value round-trip |
| FR-005 | tests/test_participant.py | Auth token hashed (bcrypt); hash stored not plaintext |
| FR-006 | tests/test_messages.py | Sequential turn numbering + advisory-lock serialization |
| FR-007 | tests/test_001_testability.py | MessageRepository has no update_*/delete_* methods |
| FR-008 | tests/test_001_testability.py | LogRepository has no update_*/delete_* methods |
| FR-009 | untested | FK constraints enforced in schema; trigger: add FK violation scenario test in Phase E |
| FR-010 | tests/test_lifecycle.py, tests/test_001_testability.py | All valid transitions tested; invalid transitions raise InvalidTransitionError |
| FR-011 | tests/test_lifecycle.py | Atomic deletion removes messages + participants; audit log preserved |
| FR-012 | tests/test_invites.py | Invite token hashed; plaintext returned once |
| FR-013 | untested | Proposal + voting schema present; trigger: add proposal lifecycle tests in fix/001-testability Phase F |
| FR-014 | untested | Interrupt queue schema present; trigger: fix/001-testability Phase F |
| FR-015 | untested | Review gate draft schema present; trigger: fix/011-testability covers the review-gate flow |
| FR-016 | tests/test_departure.py | depart_participant overwrites api_key_encrypted + nulls token |
| FR-017 | tests/test_001_testability.py | Migration 008 forward-only pass downgrade; all migrations define downgrade() |
| FR-018 | untested | Message tree (parent_turn, branch_id) schema present; trigger: branching feature Phase 3 |
| FR-019 | tests/test_lifecycle.py | admin_audit_log survives delete_session (denormalized, no FK) |
| FR-020 | tests/test_encryption.py | encrypt_value + decrypt_value; EncryptionKeyMissingError on missing key |
| FR-021 | tests/test_001_testability.py | Wrong-key decrypt raises cryptography.fernet.InvalidToken |
| FR-022 | tests/test_001_testability.py | MessageRepository + LogRepository have no mutation methods |

---

## 007-ai-security-pipeline

| FR | Test path(s) | Notes |
|---|---|---|
| FR-001 | tests/test_sanitizer.py, tests/test_corpus_fixtures.py | Every sanitizer pattern group; corpus category coverage |
| FR-002 | tests/test_sanitizer.py, tests/test_007_security_pipeline_testability.py | Round02 Cyrillic homoglyph named regression + homoglyph fold |
| FR-003 | tests/test_spotlighting.py | Spotlighting + same-speaker exemption |
| FR-004 | tests/test_output_validator.py, tests/test_007_security_pipeline_testability.py | Output validation schema contract |
| FR-005 | tests/test_output_validator.py, tests/test_007_security_pipeline_testability.py | Threshold boundary: 0.6 no-block, 0.7 block, 0.9 block |
| FR-006 | tests/test_spotlighting.py | Datamarking layer |
| FR-007 | tests/test_sanitizer.py | ChatML + role markers stripped |
| FR-008 | tests/test_exfiltration.py, tests/test_scrubber.py | Credential pattern detection + log scrubbing |
| FR-009 | tests/test_prompt_protector.py | Canary + fragment leakage detection |
| FR-010 | tests/test_prompt_protector.py | Canary generation and placement |
| FR-011 | untested | LLM-as-judge is NoOpJudge stub; trigger: Phase 3 when feature flag wired |
| FR-012 | tests/test_scrubber.py | Log scrubbing + excepthook traceback scrub |
| FR-013 | tests/test_007_security_pipeline_testability.py | Fail-closed: skip without breaker penalty + pipeline_error row (3 tests) |
| FR-014 | tests/test_007_security_pipeline_testability.py | Timing values are non-negative ints |
| FR-015 | tests/test_007_security_pipeline_testability.py, tests/test_logs.py | Detection-record schema + DB round-trip |
| FR-016 | tests/test_corpus_fixtures.py | 0% FPR on hand-curated benign corpus |
| FR-017 | untested | Pattern-list update is a process item; automated CI gate deferred to Phase 3 |
| FR-018 | untested | LLM-as-judge deferred; trigger: when NoOpJudge replaced in Phase 3 |
| FR-019 | tests/test_corpus_fixtures.py | FPR baseline on benign corpus |
| FR-020 | tests/test_007_security_pipeline_testability.py | layer_duration_ms non-negative on normal + blocked content |
| FR-021 | tests/test_corpus_fixtures.py | Adversarial corpus coverage per category |
| FR-022 | untested | pipeline_total_ms metric deferred to Phase 3 operations audit |
| FR-023 | untested | LLM-as-judge deferred (Phase 3); trigger: when NoOpJudge replaced |
