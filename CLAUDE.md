# SACP Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-20

## Active Technologies
- Python 3.11+ (constitution §6.1) + FastAPI, asyncpg, Alembic, cryptography (Fernet), bcrypt (001-core-data-model)
- PostgreSQL 16 via Docker Compose (001-core-data-model)
- bcrypt, IP binding, token expiry (002-participant-auth)
- litellm>=1.83.0, 8-mode routing, circuit breaker (003-turn-loop-engine)
- sentence-transformers, numpy — SafeTensors only (004-convergence-cadence)
- Structured JSON summarization via cheapest model (005-summarization-checkpoints)
- FastAPI SSE server, 25 endpoints, port 8750 (006-mcp-server)
- 7-layer security pipeline — sanitization, spotlighting, validation, exfiltration, jailbreak, prompt defense, log scrubbing (007-ai-security-pipeline)
- 4-tier delta system prompts with canary tokens (008-prompts-security-wiring)
- Per-participant rate limiting, 60 req/min default (009-rate-limiting)
- Web UI: FastAPI app on port 8751, WebSocket /ws/{session_id}, single-file React SPA via CDN + SRI pins (011-web-ui)

## Project Structure

```text
src/
  api_bridge/       # LiteLLM provider dispatch
  auth/             # AuthService, guards
  database/         # asyncpg pooling, Fernet encryption
  models/           # Frozen dataclasses
  repositories/     # 8 data access objects (append-only)
  orchestrator/     # Turn loop, routing, context, convergence, cadence
  security/         # 7 security modules
  prompts/          # 4-tier delta system prompt assembly
  mcp_server/       # FastAPI + 25 endpoints + rate limiter
tests/
alembic/
specs/
```

## Commands

cd src; pytest; ruff check .

## Code Style

Python 3.11+ (constitution §6.1): Follow standard conventions

## Recent Changes
- 011-web-ui: Phase 2 COMPLETE (2026-04-20) — 10 user stories shipped on port 8751, React SPA with CDN+SRI, strict CSP, HttpOnly cookie auth, WebSocket v1 event envelope, dashboards + review gate + admin + proposals
- Phase 1 COMPLETE (2026-04-20) — all scenario tests pass after PR #84
- 010 review-gate pause scope — facilitator-configurable session/participant pause, dispatch-pause while drafts pending
- 009-rate-limiting: Per-participant rate limiting middleware
- 008-prompts-security-wiring: 4-tier delta prompts + security pipeline wiring
- 007-ai-security-pipeline: Defense-in-depth security layer (7 modules)


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
