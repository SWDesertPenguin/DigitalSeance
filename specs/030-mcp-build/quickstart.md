# Quickstart: MCP Build

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-05-13

End-to-end smoke-test scenarios for each phase. These are the runs an operator executes on the freshly-merged PR to confirm the phase landed cleanly.

## Phase 1 — Codebase Restructure smoke

Verifies the rename landed cleanly and the running stack still works.

```bash
# 1. confirm directory rename
ls src/                                  # → must include participant_api/ and mcp_protocol/; must NOT include mcp_server/

# 2. confirm zero residual references
git grep "mcp_server" -- src/ tests/ docs/ alembic/      # → 0 hits

# 3. confirm import paths resolve
python -c "from src.participant_api import create_participant_api_app; print('ok')"
python -c "from src.mcp_protocol import __doc__; print(__doc__)"        # → placeholder docstring

# 4. confirm git history follows the rename
git log --follow src/participant_api/app.py | head -5    # → commits pre-dating the refactor

# 5. confirm both ASGI apps start
python -m src.run_apps &
RUN_PID=$!
sleep 5
curl -s http://localhost:8750/healthz                    # → 200
curl -s http://localhost:8751/healthz                    # → 200
kill $RUN_PID

# 6. confirm SSE shape unchanged
# (manual: connect a participant client and confirm {turn, speaker_id, action, skipped} payload)
```

If any step fails: Phase 1 is NOT cleanly landed; do not proceed to Phases 2–4.

## Phase 2 — MCP Protocol smoke

Verifies the MCP endpoint speaks Streamable HTTP and the `initialize` → `tools/list` → `tools/call` handshake completes.

```bash
# 1. set environment
export SACP_MCP_PROTOCOL_ENABLED=true
export SACP_MCP_MAX_CONCURRENT_SESSIONS=5     # test-config tight cap
export SACP_BEARER=<test bearer issued from a known session>

# 2. discovery
curl -s http://localhost:8750/.well-known/mcp-server | jq .       # → {"enabled": true, "protocol_version": "2025-11-25", ...}

# 3. initialize
INIT_RES=$(curl -s -i -X POST http://localhost:8750/mcp \
  -H "Authorization: Bearer $SACP_BEARER" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"smoke","version":"1.0"}},"id":"1"}')

SESSION=$(echo "$INIT_RES" | grep -i "mcp-session-id:" | cut -d' ' -f2 | tr -d '\r')
echo "Session: $SESSION"                                          # → 64-char hex

# 4. tools/list
curl -s -X POST http://localhost:8750/mcp \
  -H "Authorization: Bearer $SACP_BEARER" \
  -H "Mcp-Session-Id: $SESSION" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":"2"}' | jq '.result.tools | length'   # → > 0

# 5. tools/call (canonical test tool)
curl -s -X POST http://localhost:8750/mcp \
  -H "Authorization: Bearer $SACP_BEARER" \
  -H "Mcp-Session-Id: $SESSION" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"session.list","arguments":{}},"id":"3"}' | jq .

# 6. master-switch-off check
unset SACP_MCP_PROTOCOL_ENABLED
# (restart server)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8750/mcp -X POST   # → 404
curl -s http://localhost:8750/healthz                                       # → 200 (participant_api unaffected)

# 7. concurrent-session-cap check (cap = 5)
# (loop: open 6 initialize calls; 6th must return HTTP 503 + Retry-After header)
```

## Phase 3 — Tool Mapping smoke

Verifies every public participant_api route has at least one MCP tool counterpart (FR-068 architectural test) and the dispatch path matches behavior.

```bash
# Run the architectural test directly
pytest tests/test_mcp_tools_parity.py -v       # → all PASS
pytest tests/test_mcp_tools_session.py -v
pytest tests/test_mcp_tools_participant.py -v
pytest tests/test_mcp_tools_proposal.py -v
# ... etc per category

# Idempotency smoke
# (call session.create twice with the same _idempotency_key; second call must return the original result without re-executing)

# Per-category disable check
export SACP_MCP_TOOL_DEBUG_EXPORT_ENABLED=false
# (restart; confirm debug.export_session is absent from tools/list and call_tool returns SACP_E_NOT_FOUND)
```

## Phase 4 — OAuth Flow smoke

Verifies the full OAuth Authorization Code + PKCE flow + refresh rotation + revocation.

```bash
# 1. discovery
curl -s http://localhost:8750/.well-known/oauth-protected-resource | jq .

# 2. authorize (PKCE)
CODE_VERIFIER=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
CODE_CHALLENGE=$(python -c "import hashlib, base64; print(base64.urlsafe_b64encode(hashlib.sha256(b'$CODE_VERIFIER').digest()).decode().rstrip('='))")
echo "verifier: $CODE_VERIFIER"
echo "challenge: $CODE_CHALLENGE"

# (manual: navigate browser to /authorize?... ; complete email+password; obtain code from redirect)

# 3. exchange code for tokens
AUTH_CODE=<from redirect>
TOKEN_RES=$(curl -s -X POST http://localhost:8750/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=$AUTH_CODE&code_verifier=$CODE_VERIFIER&redirect_uri=http://localhost:9999/callback&client_id=<client_id>")
ACCESS=$(echo "$TOKEN_RES" | jq -r .access_token)
REFRESH=$(echo "$TOKEN_RES" | jq -r .refresh_token)

# 4. use access token against the MCP endpoint
curl -s -X POST http://localhost:8750/mcp -H "Authorization: Bearer $ACCESS" ...

# 5. refresh
NEW_TOKEN_RES=$(curl -s -X POST http://localhost:8750/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token&refresh_token=$REFRESH&client_id=<client_id>")
NEW_REFRESH=$(echo "$NEW_TOKEN_RES" | jq -r .refresh_token)
echo "Old refresh rotated; new: ${NEW_REFRESH:0:16}..."

# 6. confirm replay revokes family
curl -s -X POST http://localhost:8750/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token&refresh_token=$REFRESH&client_id=<client_id>" | jq .
# → {"error":"invalid_grant"}; entire token family now revoked

# 7. revoke
curl -s -X POST http://localhost:8750/revoke \
  -d "token=$NEW_REFRESH&client_id=<client_id>"      # → HTTP 200, empty body

# 8. confirm step-up on destructive action
# (use a stale access token to invoke admin.archive_session; expect SACP_E_STEP_UP_REQUIRED error)
```

## Phase 5 — Onboarding Doc smoke

Verifies the docs are present, samples parse as JSON, redaction policy is honored, and walk-through fits the time budget.

```bash
# 1. doc presence
ls docs/participant-onboarding.md
ls docs/participant-onboarding-windows.md
ls docs/participant-onboarding-macos.md

# 2. version header check
head -5 docs/participant-onboarding.md           # → must include SACP Phase, Last Updated, Tested Against

# 3. sample JSON parse
# (extract the claude_desktop_config.json sample from each platform doc; pipe through `jq .`)

# 4. redaction policy check
grep -E "SACP_DOC_EXAMPLE_[A-Za-z0-9]{32}|000000000000|orchestrator\.example" docs/participant-onboarding*.md
# → all placeholders use the prefix pattern; no real-shape tokens

# 5. troubleshooting matrix entries
grep -E "^\| 40[134]|^\| Timeout" docs/participant-onboarding.md
# → 401, 403, 404, Timeout entries present

# 6. cross-references
grep -E "\[Phase [1-4]\]|\(phase-[1-4]\)" docs/participant-onboarding.md
# → all four phase refs present

# 7. walk-through (manual)
# (a non-Spike Windows participant follows the doc end-to-end; stopwatch reads ≤ 15 min)
# (a non-Spike macOS participant follows the doc end-to-end; stopwatch reads ≤ 15 min)
```

## Closeout preflights (every phase merge PR)

Run before opening the merge PR per `feedback_closeout_preflight_scripts`:

```powershell
.\scripts\preflight-traceability.ps1
.\scripts\preflight-doc-deliverables.ps1
.\scripts\preflight-audit-label-parity.ps1
.\scripts\preflight-detection-taxonomy-parity.ps1
.\scripts\preflight-migration-chain.ps1
# Plus the two newer preflights per FR-013
```

All five (or seven, with the newer additions) MUST be green before merge.
