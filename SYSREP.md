# SACP System Report

**Last Updated**: 2026-04-12

## Project Overview

| Item | Value |
|------|-------|
| **Project** | DigitalSeance / SACP (Sovereign AI Collaboration Protocol) |
| **Constitution** | v0.5.1, ratified 2026-04-11 |
| **Phase** | Phase 1 (MVP) — core implemented, hardening remaining |
| **Server** | Running on Dockge via GHCR image |
| **Port** | 8750 (MCP Server / FastAPI) |
| **Image** | `ghcr.io/swdesertpenguin/digitalseance:latest` |

## Features

| # | Feature | Status | Stories | Tasks |
|---|---------|--------|---------|-------|
| 001 | Core Data Model | Merged | 9 | 42/42 |
| 002 | Participant Auth | Merged | 8 | 30/30 |
| 003 | Turn Loop Engine | Merged | 10 | 26/26 |
| 004 | Convergence Detection | Merged | 5 | 17/17 |
| 005 | Summarization Checkpoints | Merged | 5 | 12/12 |
| 006 | MCP Server | Merged | 7 | 14/14 |

## Codebase Stats

| Metric | Count |
|--------|-------|
| Source files (src/) | ~40 |
| Test files (tests/) | ~25 |
| Lines of Python | ~8,500 |
| Spec/plan/task docs | ~30 |
| PRs merged | 10 |
| Database tables | 13 |
| API endpoints | 18 |
| Routing modes | 8 |
| Test results (non-DB) | 69/69 passing |

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
└── mcp_server/                  # FastAPI app + tool endpoints
```

## API Endpoints

### Session Tools
- `POST /tools/session/create` — create a new session
- `POST /tools/session/pause` — pause active session
- `POST /tools/session/resume` — resume paused session
- `POST /tools/session/archive` — archive session (read-only)
- `POST /tools/session/start_loop` — start conversation loop
- `POST /tools/session/stop_loop` — stop conversation loop
- `GET /tools/session/export_markdown` — export transcript
- `GET /tools/session/export_json` — export as JSON

### Participant Tools
- `POST /tools/participant/inject_message` — human interjection
- `GET /tools/participant/status` — session status
- `GET /tools/participant/history` — conversation history
- `GET /tools/participant/summary` — latest checkpoint
- `POST /tools/participant/set_routing_preference` — change routing
- `POST /tools/participant/rotate_token` — rotate auth token

### Facilitator Tools
- `POST /tools/facilitator/create_invite` — generate invite link
- `POST /tools/facilitator/approve_participant` — approve pending
- `POST /tools/facilitator/reject_participant` — reject pending
- `POST /tools/facilitator/remove_participant` — remove active
- `POST /tools/facilitator/revoke_token` — force-revoke token
- `POST /tools/facilitator/transfer_facilitator` — transfer role

## Infrastructure

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.11, FastAPI |
| Database | PostgreSQL 16 (Docker) |
| Provider Abstraction | LiteLLM ≥1.83.0 |
| Embeddings | sentence-transformers (MiniLM-L6-v2) |
| Encryption | Fernet (AES-128-CBC + HMAC-SHA256) |
| Token Hashing | bcrypt (cost factor 12) |
| Migrations | Alembic (2 migrations) |
| CI/CD | GitHub Actions → GHCR |
| Deployment | Docker Compose via Dockge |
| Pre-commit | 13 hooks (gitleaks, ruff, bandit, 25/5 lint) |

## Phase 1 Remaining

- [ ] AI security pipeline (spotlighting, sanitization, trust tiers)
- [ ] System prompt management (4-tier delta with canary tokens)
- [ ] Log scrubbing (credential redaction before emission)
- [ ] Integration testing with real providers
- [ ] Rate limiting per participant
- [ ] Database tests (need PostgreSQL for test suite)

## Open Branches

None — main is clean.

## Constitution Compliance

All 11 validation gates pass on every feature:
- V1 Sovereignty | V2 No cross-phase | V3 Security hierarchy
- V4 Facilitator bounded | V5 Transparency | V6 Graceful degradation
- V7 Coding standards | V8 Data security | V9 Log integrity
- V10 AI security (partial) | V11 Supply chain
