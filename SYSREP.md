# SACP System Report

**Last Updated**: 2026-04-17

## Project Overview

| Item | Value |
|------|-------|
| **Project** | DigitalSeance / SACP (Sovereign AI Collaboration Protocol) |
| **Constitution** | v0.5.1, ratified 2026-04-11 |
| **Phase** | Phase 1 — TESTING (code complete, live validation in progress) |
| **Server** | Running on Dockge via GHCR image |
| **Port** | 8750 (MCP Server / FastAPI) |
| **Image** | `ghcr.io/swdesertpenguin/digitalseance:latest` |
| **Main** | `af477e2` (PRs #45-64 merged) |

## Features

| # | Feature | Status | Stories | Tasks |
|---|---------|--------|---------|-------|
| 001 | Core Data Model | Merged | 9 | 42/42 |
| 002 | Participant Auth | Merged | 8 | 30/30 |
| 003 | Turn Loop Engine | Merged | 10 | 26/26 |
| 004 | Convergence Detection | Merged | 5 | 17/17 |
| 005 | Summarization Checkpoints | Merged | 5 | 12/12 |
| 006 | MCP Server | Merged | 7 | 14/14 |
| 007 | AI Security Pipeline | Merged | 7 | 20/20 |
| 008 | System Prompts + Security Wiring | Merged | 3 | — |
| 009 | Rate Limiting | Merged | 1 | — |
| 011 | Web UI | Spec Draft | 8 | — |

## Codebase Stats

| Metric | Count |
|--------|-------|
| Source files (src/) | 63 |
| Test files (tests/) | 45 |
| Lines of Python (total) | ~11,100 |
| Lines of Python (src/) | ~6,300 |
| Lines of Python (tests/) | ~4,800 |
| Spec/plan/task docs | ~50 |
| PRs merged | 64 |
| Database tables | 13 |
| API endpoints | 28 |
| Routing modes | 8 |
| Security modules | 7 |
| Test results (non-DB) | 120+ passing |

## Architecture

```
src/
├── config.py                    # Environment settings
├── database/                    # asyncpg pool, Fernet encryption
├── models/                      # Frozen dataclasses (7 entity types)
├── repositories/                # Data access (8 repositories)
├── auth/                        # AuthService, guards
├── orchestrator/                # Turn loop, routing, context, convergence
├── api_bridge/                  # LiteLLM provider dispatch
├── mcp_server/                  # FastAPI app + tool endpoints + rate limiter
├── security/                    # Sanitizer, spotlighting, validator, exfiltration, jailbreak, prompt protector, scrubber
└── prompts/                     # 4-tier delta system prompt assembly
```

## API Endpoints

### Session Tools
- `POST /tools/session/create` — create a new session (human facilitator default)
- `POST /tools/session/pause` — pause active session
- `POST /tools/session/resume` — resume paused session
- `POST /tools/session/archive` — archive session (read-only)
- `POST /tools/session/start_loop` — start conversation loop
- `POST /tools/session/stop_loop` — stop conversation loop
- `GET /tools/session/summary` — latest structured summarization checkpoint (any participant)
- `GET /tools/session/export_markdown` — export transcript
- `GET /tools/session/export_json` — export as JSON

### Participant Tools
- `POST /tools/participant/inject_message` — human interjection (works while paused)
- `GET /tools/participant/status` — session status
- `GET /tools/participant/history` — conversation history
- `GET /tools/participant/summary` — latest checkpoint
- `POST /tools/participant/rotate_token` — rotate auth token

### Facilitator Tools
- `POST /tools/facilitator/add_participant` — add AI participant (with budget fields)
- `POST /tools/facilitator/create_invite` — generate invite link
- `POST /tools/facilitator/approve_participant` — approve pending
- `POST /tools/facilitator/reject_participant` — reject pending
- `POST /tools/facilitator/remove_participant` — remove active
- `POST /tools/facilitator/revoke_token` — force-revoke token
- `POST /tools/facilitator/transfer_facilitator` — transfer role
- `POST /tools/facilitator/set_routing_preference` — change participant routing mode
- `POST /tools/facilitator/set_budget` — set participant budget limits
- `POST /tools/facilitator/set_review_gate_pause_scope` — toggle session-wide vs participant-only pause while drafts are pending
- `GET /tools/facilitator/list_drafts` — list pending review-gate drafts
- `POST /tools/facilitator/approve_draft` — approve a staged draft (writes to transcript)
- `POST /tools/facilitator/reject_draft` — reject a staged draft (discard)
- `POST /tools/facilitator/edit_draft` — edit and approve a staged draft
- `POST /tools/facilitator/debug_set_timeouts` — prime a participant's consecutive_timeouts counter for circuit-breaker testing

### Debug Tools
- `GET /tools/debug/export` — full session export (facilitator only)

## Infrastructure

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.11, FastAPI |
| Database | PostgreSQL 16 (Docker) |
| Provider Abstraction | LiteLLM >=1.83.0 |
| Embeddings | sentence-transformers (MiniLM-L6-v2) |
| Encryption | Fernet (AES-128-CBC + HMAC-SHA256) |
| Token Hashing | bcrypt (cost factor 12) |
| Migrations | Alembic (5 migrations through 005_session_review_gate_pause_scope) |
| CI/CD | GitHub Actions -> GHCR |
| Deployment | Docker Compose via Dockge |
| Pre-commit | 13 hooks (gitleaks, ruff, bandit, 25/5 lint) |

## Phase 1 Status

Phase 1 COMPLETE. All features implemented; all scenario tests pass.

- [x] Core data model (13 tables, 8 repositories)
- [x] Participant auth (tokens, approval, rotation, IP binding)
- [x] Turn loop engine (8 routing modes, context assembly, LiteLLM)
- [x] Convergence detection (embeddings, cadence, adversarial rotation)
- [x] Summarization checkpoints (structured JSON)
- [x] MCP server (25 endpoints, SSE)
- [x] AI security pipeline (sanitization, spotlighting, validation, exfiltration, jailbreak, prompt protection, log scrubbing)
- [x] System prompt management (4-tier delta with canary tokens)
- [x] Security pipeline integrated into turn loop + context assembly
- [x] Rate limiting (per-participant, 60 req/min default)

## Live Testing Progress

Scenario 1 (1 AI): 9/9 PASS. Scenario 2 (2 AIs): 6/6 PASS. Scenario 3 (multi-AI + closeout):
T3.1 partial (invite accept deferred to Phase 2), T3.2 / T3.3 / T3.4 / T3.5 / T3.6 PASS.
See `test-plan-phase1.md` for full test plan and status.

## Post-Deployment Fixes (PRs #28-84)

| PR Range | Fixes |
|----------|-------|
| #28-37 | API key to body, dynamic branch ID, context markers, Ollama dispatch, IPv4 |
| #38-44 | Feature completions (prompts, security, rate limiting) |
| #45-58 | Spec plans, task docs, context updates |
| #59 | routing_log turn numbers, empty response guard, budget fields, human facilitator |
| #60 | cost_usd tracking, graceful pause, observer skip action |
| #61-62 | set_routing_preference moved to facilitator endpoint + fix |
| #63 | Skip spin delay (5s min sleep for skipped turns, dedup skip logs) |
| #64 | inject-on-pause fix, current_turn sync, set_routing/set_budget 404 guard |
| #65-66 | Swagger add_participant placeholder rejection, alembic migration 004 |
| #67-69 | Degenerate output detection, convergence skip-turn guard, divergence prompt injection |
| #70-72 | Review gate approve/reject/edit endpoints, dispatch-pause + configurable scope, conftest alembic mirror |
| #73-74 | Session-scope pause blocks all speakers, pause actually stops loop, set_routing Literal, skip just-resolved participant |
| #75 | export_markdown/export_json fixed to use get_main_branch_id |
| #76 | Multi-stage Dockerfile + .dockerignore + add_participant human defaults |
| #77 | Exclude provider='human' from round-robin dispatch |
| #78-79 | Claude empty-response fix (role mapping + no_new_input guard) + first-turn allow |
| #80-81 | Context chronological ordering (fill_history was appending older turns) + attribute fix |
| #82 | Wire SummarizationManager into loop, threshold 50→10, GET /tools/session/summary, debug_set_timeouts |
| #83 | Summarizer excludes human participants when picking cheapest model |
| #84 | Strip markdown code fences before parsing summarizer JSON |

## Phase 2 — Web UI (Planned)

Spec drafted at `specs/011-web-ui/spec.md`. Needs plan.md + tasks.md.

- 8 user stories, 17 functional + 8 security requirements
- Internal phasing: 2a (core), 2b (dashboard), 2c (workflows)
- Single-file React JSX, no build toolchain, port 8751
- Phases: 2a = login + transcript + WebSocket + controls, 2b = budget + convergence + admin, 2c = review gate + proposals + export

## Constitution Compliance

All 11 validation gates fully pass:
- V1 Sovereignty | V2 No cross-phase | V3 Security hierarchy
- V4 Facilitator bounded | V5 Transparency | V6 Graceful degradation
- V7 Coding standards | V8 Data security | V9 Log integrity
- V10 AI security (FULL) | V11 Supply chain
