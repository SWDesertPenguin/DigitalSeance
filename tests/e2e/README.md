# Phase 2 Web UI — Playwright e2e

Browser-driving regression tests for the 10 Phase 2 user stories.
Skipped by default; opt in with `SACP_RUN_E2E=1` so CI matrices without
browser infrastructure don't trip.

## What's here

| File | User story | Task ID |
|---|---|---|
| `test_us1_facilitator_flow.py` | US1 — facilitator login, transcript, inject, pause | T058 |
| _(future)_ `test_us2_participant_view.py` | US2 — role gating | T074 |
| _(future)_ `test_us3_websocket_reconnect.py` | US3 — reconnect + resync | T085 |
| _(future)_ `test_us8_xss_vectors.py` | US8 — XSS + ZWS + javascript: link | T094 |
| _(future)_ `test_us4_dashboard.py` | US4 — budget + convergence | T103 |
| _(future)_ `test_us5_review_gate.py` | US5 — approve/edit/reject | T115 |
| _(future)_ `test_us6_admin_panel.py` | US6 — admin workflows | T126 |
| _(future)_ `test_us9_summary.py` | US9 — summary viewer | T134 |
| _(future)_ `test_us10_health.py` | US10 — health indicators | T143 |
| _(future)_ `test_us7_proposals.py` | US7 — voting | T154 |

The first file is the reference template — subsequent US tests follow
the same fixture shape (`signed_in_page` from `conftest.py`).

## Local run

```bash
# 1. Install playwright + the browser binary
uv pip install -e '.[e2e]'
playwright install chromium

# 2. Start the stack
docker compose up -d

# 3. Create a session, capture its facilitator token
export SACP_E2E_FACILITATOR_TOKEN=$(curl -s -XPOST \
    http://localhost:8750/tools/session/create \
    -H 'Content-Type: application/json' \
    -H 'X-SACP-Request: 1' \
    -d '{"name":"e2e","display_name":"Tester"}' | jq -r .auth_token)

# 4. Run the suite
SACP_RUN_E2E=1 pytest tests/e2e/ -v
```

Set `SACP_WEB_UI_BASE_URL` / `SACP_MCP_BASE_URL` if running against a
remote deployment rather than localhost defaults.

## CI notes

Add a separate GitHub Actions job (not the default `pytest` job) that:

1. `pip install -e '.[e2e]'`
2. `playwright install --with-deps chromium`
3. `docker compose up -d --wait`
4. Provisions a throwaway session + token
5. `SACP_RUN_E2E=1 pytest tests/e2e/ -v`

Keep the existing unit-test job unchanged — it should remain fast and
not require browser / docker infrastructure.

## Authoring new tests

- Use the `signed_in_page` fixture for anything that needs an
  authenticated session. It handles AuthGate → SessionView.
- Target DOM structure by class (`.participant-list`, `.transcript`,
  `.msg-body`) or `get_by_role` / `get_by_text`. Avoid brittle CSS
  indexing.
- WebSocket-driven UI changes are eventually-consistent — always wait
  with `page.wait_for_selector` / `wait_for_function` with a bounded
  timeout (≤5 s for turn-based events, ≤30 s for reconnect flows).
- Assert against data the server controls (turn numbers, participant
  ids) whenever possible. Don't hardcode AI response text.
