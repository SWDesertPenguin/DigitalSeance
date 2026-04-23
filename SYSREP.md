# SACP System Report

**Last Updated**: 2026-04-23 (Phase 2 shakedown through Test06-Web07)

## Project Overview

| Item | Value |
|------|-------|
| **Project** | DigitalSeance / SACP (Sovereign AI Collaboration Protocol) |
| **Constitution** | v0.5.1, ratified 2026-04-11 |
| **Phase** | Phase 2 — SHAKEDOWN (Web UI shipped 2026-04-20; 6 sweep PRs through 2026-04-22) |
| **Server** | Two-app FastAPI process on Dockge via GHCR image |
| **Ports** | 8750 (MCP server / SSE) + 8751 (Web UI / WebSocket) |
| **Image** | `ghcr.io/swdesertpenguin/digitalseance:latest` |
| **Main** | `8e71e41` (PR #112 merged — Test06-Web07 sweep) |

## Features

| # | Feature | Status | Stories | Notes |
|---|---------|--------|---------|-------|
| 001 | Core Data Model | Merged | 9 | PostgreSQL 16, 13 tables, 8 repositories |
| 002 | Participant Auth | Merged | 8 | bcrypt, IP binding, token expiry, rotation |
| 003 | Turn Loop Engine | Merged | 10 | 8 routing modes, circuit breaker |
| 004 | Convergence Detection | Merged | 5 | MiniLM-L6-v2 SafeTensors, cadence, adversarial rotation |
| 005 | Summarization Checkpoints | Merged | 5 | structured JSON, cheapest model |
| 006 | MCP Server | Merged | 7 | FastAPI + SSE, port 8750 |
| 007 | AI Security Pipeline | Merged | 7 | 7 modules (sanitize, spotlight, validate, exfil, jailbreak, prompt defense, scrub) |
| 008 | System Prompts + Security Wiring | Merged | 3 | 4-tier delta, canary tokens |
| 009 | Rate Limiting | Merged | 1 | per-participant, 60 req/min default |
| 010 | Review-gate Pause Scope | Merged | — | session / participant toggle |
| 011 | Web UI | Merged (+7 shakedown sweeps) | 10 | port 8751, React SPA + CDN/SRI, WebSocket v1 envelope |

## Codebase Stats

| Metric | Count |
|--------|-------|
| Source files (`src/`) | 73 |
| Test files (`tests/`) | 52 |
| Lines of Python (`src/`) | ~9,750 |
| Lines of Python (`tests/`) | ~5,700 |
| Database tables | 13 |
| Alembic migrations | 5 |
| API endpoints (MCP + Web UI) | 51 |
| Routing modes | 8 |
| Security modules | 7 |
| Test results | 191 pass / 114 skip (Postgres-gated) locally; CI runs the skipped set |
| Commits on `main` | 256 |

## Architecture

```
src/
├── api_bridge/     # LiteLLM provider dispatch
├── auth/           # AuthService, guards
├── database/       # asyncpg pool, Fernet encryption
├── models/         # Frozen dataclasses (entity types)
├── repositories/   # 8 data access objects (append-only transcripts)
├── orchestrator/   # Turn loop, routing, context, convergence, cadence, summarizer, branch, budget, circuit breaker
├── security/       # 7 security modules
├── prompts/        # 4-tier delta system prompt assembly
├── mcp_server/     # FastAPI app on 8750 + tool routers + rate limiter
└── web_ui/         # FastAPI app on 8751 + auth, events, websocket, snapshot, security headers
run_apps.py         # dual-uvicorn via asyncio.gather
```

## API Endpoints

### Session Tools (`/tools/session/*`)
- `POST /create` — create a new session (human facilitator default)
- `POST /request_join` — public request for pending role
- `POST /redeem_invite` — swap invite token → pre-approved participant
- `POST /set_name` — facilitator rename
- `POST /pause` / `POST /resume` / `POST /archive` — lifecycle (archive auto-summarizes)
- `POST /start_loop` / `POST /stop_loop` — loop control
- `GET /loop_status` — is the loop running?
- `POST /summarize_now` — facilitator force-checkpoint (serialized per session)
- `GET /summary` — latest structured summarization checkpoint (any participant)
- `GET /export_markdown` / `GET /export_json` — transcript export

### Participant Tools (`/tools/participant/*`)
- `POST /inject_message` — human interjection (works while paused)
- `GET /status` — session status
- `GET /history` — conversation history
- `GET /summary` — latest checkpoint
- `POST /rotate_my_token` — self-rotate (returns new bearer)
- `POST /rotate_token` — facilitator-triggered rotation (legacy)
- `POST /add_ai` — non-facilitator adds own sponsored AI
- `POST /set_routing_preference` — caller mutates own row

### Facilitator Tools (`/tools/facilitator/*`)
- `POST /add_participant` — add AI or human (with budget fields)
- `POST /create_invite` — generate invite link
- `POST /approve_participant` / `POST /reject_participant` / `POST /remove_participant`
- `POST /revoke_token` — force-revoke + close target's WebSockets with 4401
- `POST /transfer_facilitator` — transfer role; renames `Facilitator-` prefix accordingly
- `POST /set_routing_preference` — facilitator or sponsor edits any AI's mode
- `POST /set_routing_all_ais` — bulk flip every AI's routing (review_gate / always)
- `POST /set_budget` — facilitator or sponsor; 0 normalized to null (no cap)
- `POST /set_review_gate_pause_scope` — session-wide vs participant-only pause
- `POST /set_cadence_preset` — sprint/cruise/idle
- `POST /set_acceptance_mode` — unanimous/majority
- `POST /set_min_model_tier` — low/mid/high/max
- `POST /set_complexity_classifier_mode` — pattern/llm
- `POST /debug_set_timeouts` — prime consecutive_timeouts for circuit-breaker testing
- `GET /list_drafts` — list pending review-gate drafts
- `POST /approve_draft` / `POST /reject_draft` / `POST /edit_draft`

### Proposal Tools (`/tools/proposal/*`)
- `POST /create` — new proposal
- `POST /vote` — accept/reject/abstain
- `POST /resolve` — facilitator-only resolution
- `GET /list` — open + resolved proposals with tallies

### Web UI (port 8751)
- `POST /login` — bearer token → HttpOnly signed cookie + returned plaintext for MCP bearer auth
- `POST /logout` — clear cookie
- `GET /me` — cookie-restore (returns token without rotation so logout+relogin works)
- `GET /ws/{session_id}` — push-only WebSocket with v1 event envelope

### Debug Tools (`/tools/debug/*`)
- `GET /export` — full session export (facilitator only)

## Infrastructure

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.11, FastAPI |
| Database | PostgreSQL 16 (Docker) |
| Provider Abstraction | LiteLLM >= 1.83.0 |
| Embeddings | sentence-transformers (MiniLM-L6-v2, SafeTensors only) |
| Encryption | Fernet (AES-128-CBC + HMAC-SHA256) for API keys |
| Token Hashing | bcrypt (cost factor 12) |
| Migrations | Alembic (5 migrations, 001 through 005_session_review_gate_pause_scope) |
| CI/CD | GitHub Actions → GHCR |
| Deployment | Docker Compose via Dockge |
| Pre-commit | 13 hooks (gitleaks, ruff, bandit, 25-line / 5-arg coding-standards lint) |

## Phase 1 Status

Phase 1 COMPLETE (2026-04-20). All scenario tests pass.

- [x] Core data model (13 tables, 8 repositories, append-only transcripts)
- [x] Participant auth (tokens, approval, rotation, IP binding)
- [x] Turn loop engine (8 routing modes, context assembly, LiteLLM)
- [x] Convergence detection (embeddings, cadence, adversarial rotation)
- [x] Summarization checkpoints (structured JSON, summaries excluded from own input)
- [x] MCP server (SSE, authoritative API surface)
- [x] AI security pipeline (sanitization, spotlighting, validation, exfiltration, jailbreak, prompt defense, log scrubbing)
- [x] System prompt management (4-tier delta with canary tokens)
- [x] Security pipeline integrated into turn loop + context assembly
- [x] Rate limiting (per-participant, 60 req/min default)

## Phase 2 Status — Web UI

Two FastAPI apps in one process via `src/run_apps.py`:
- **MCP server** on 8750 — unchanged Phase 1 contract + proposal/session-config/self-serve routing endpoints.
- **Web UI** on 8751 — single-file React SPA from `frontend/` (CDN-loaded React 18 / Babel / marked / DOMPurify, SRI pins via `scripts/generate_sri_hashes.sh`), strict CSP, HttpOnly cookie auth, `POST /login` + `POST /logout` + `GET /me`, `GET /ws/{session_id}` WebSocket with v1 event envelope.

Ten user stories shipped (US1 facilitator flow, US2 participant view, US3 WS resilience, US4 budget / convergence, US5 review gate, US6 admin panel, US7 proposals, US8 XSS hardening, US9 summary viewer, US10 health indicators). Playwright e2e (T058/T074/T085/T094/T103/T115/T126/T134/T143) deferred to a shared-infra PR.

Seven in-anger shakedown sweeps (2026-04-20 → 2026-04-23):

| Sweep | PR | Ships |
|---|---|---|
| Test06 initial + ops | #98/#99/#100/ux-polish/test06-sweep | guest landing, invite redeem, layout pinning, skip backoff, invited_by attribution |
| Session restore | #103 | cookie F5 restore, transfer_facilitator broadcasts, Show-my-token |
| Web03 | #105 | rotate_my_token cascade fix, sponsor perms, revoke boot, dedupe 409s, prefix swap |
| Web04 | #106 | re-login after logout, budget 0 = no cap, decimal formatting, Summarize-now + Review-gate-all + Archive-confirm + session ID |
| Web05 | #108 | archive auto-summary order fix, summarize_now per-session lock, addressed_only actually matches @name |
| Web06 | #110 | summary feedback loop closed, participant_removed event, hourly-only budget renders |
| Web07 | #112 | review_gate one-shot auto-revert (prior routing cached + restored), remove_participant cascades to sponsored AIs, pending user sees denial + redirect to landing |

## Phase 3 — Planned (not started)

Per constitution §10: branching UI, sub-sessions, OAuth 2.1 with PKCE, MCP-to-MCP topology 7, Ollama/vLLM per-participant URL, Vaire shared-memory integration, step-up authorization. Requires a new Speckit cycle (`012-...`).

## Constitution Compliance

All 11 validation gates fully pass:
- V1 Sovereignty | V2 No cross-phase | V3 Security hierarchy
- V4 Facilitator bounded | V5 Transparency | V6 Graceful degradation
- V7 Coding standards | V8 Data security | V9 Log integrity
- V10 AI security (FULL) | V11 Supply chain

## Docs on Disk

- `README.md` — product entry + problem statement.
- `SACP-Exec-Summary.md` — executive overview of what SACP is and the current status.
- `SYSREP.md` — this file (system state snapshot).
- `CLAUDE.md` — auto-generated agent context.
- `SECURITY.md` — security policy.
- `docs/user-guide.md` — shakedown-tester user guide.
- `docs/phase2-test-playbook.md` — operator shakedown script.
- `docs/red-team-runbook.md` — 70+ attacks keyed to the 7-layer security pipeline; re-runnable after any security change.
- `docs/testing-runbook.md` — general testing runbook.
- `docs/AI_attack_surface_analysis_for_SACP_orchestrator.md` — threat-model analysis.
- `docs/sacp-design.md`, `docs/sacp-system-prompts.md`, `docs/sacp-use-cases.md`, `docs/sacp-communication-topologies.md` — design docs.
- GitHub wiki — hosted at `https://github.com/SWDesertPenguin/DigitalSeance.wiki.git` (separate repo, not part of the main tree).
