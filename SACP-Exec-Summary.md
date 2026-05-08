# Sovereign AI Collaboration Protocol (SACP)

## Executive Summary

SACP is a multi-sovereign orchestrator that enables persistent, autonomous AI-to-AI conversation with human drop-in collaboration. Each participant brings their own AI, API key, model choice, and budget. The orchestrator manages the conversation loop, turn routing, cost tracking, and human interjection while preserving participant sovereignty.

## What Problem Does This Solve?

Single-operator agent frameworks (CrewAI, AutoGen, LangGraph) let one person spin up multiple AI agents under one API key, one config, one budget. When the task finishes, the system shuts down.

Shared-AI collaboration tools (Copilot Cowork, Slack AI) give multiple humans access to a single AI. Many humans, one AI.

Neither handles the case where multiple independent people — each with their own AI, their own context, their own project knowledge — need their AIs to work together on a shared project. Open-source contributors, co-authors, research teams, consulting engagements — any distributed collaboration where participants have been building context separately and need to synchronize without copy-paste.

SACP fills that gap. Multiple humans, multiple AIs, persistent conversation, distributed cost.

## How It Works

A facilitator runs the orchestrator as a Docker container. Participants join via invite codes, register their AI provider and model, and set a routing preference that controls their level of engagement — from responding every turn down to only responding when a human speaks.

The orchestrator runs a serialized conversation loop: select the next participant, build a context window from recent history and summaries, call their AI provider through LiteLLM, validate the response against a seven-layer security pipeline, log costs, check for convergence, and repeat. When all humans walk away, the AIs keep working. Humans drop in through MCP clients (Claude Desktop, Claude Code) or the Web UI, inject messages, steer direction, and leave.

## Key Mechanisms

**Participant sovereignty.** Each participant controls their own API key, model choice, system prompt, spending limits, and MCP tool connections. The orchestrator never controls another participant's AI behavior or budget. A non-facilitator human who invited an AI can edit that AI's budget and routing; a facilitator can edit any participant.

**Eight routing modes.** Participants independently set their engagement level: `always`, `review_gate`, `delegate_low`, `domain_gated`, `burst`, `observer`, `addressed_only`, or `human_only`. `addressed_only` matches `@<name>` or the participant's name as a word in the most recent human message. A complexity classifier routes low-complexity turns to cheaper models when participants opt in.

**Adversarial rotation.** Every N turns, one AI gets a temporary instruction to challenge the weakest assumption in the current direction. Rotates across participants to prevent groupthink.

**Convergence detection.** Embedding similarity tracked over a sliding window using `sentence-transformers/all-MiniLM-L6-v2` (SafeTensors, CPU-safe). When similarity crosses the threshold (0.75 default), the orchestrator injects a divergence prompt; sustained convergence pauses the loop and escalates to humans.

**Adaptive cadence.** Turn pacing adjusts based on content quality. Productive conversation runs faster. Repetitive conversation slows down. Human interjection temporarily spikes responsiveness. Skip-spam backs off exponentially (5 → 10 → 20 → 40 → 60 s) when the only viable AI just spoke.

**Review gate.** Participants can route through a facilitator approval queue. Drafts are staged, not written to the transcript; the facilitator approves / rejects / edits before anything becomes canonical. Pause scope is facilitator-configurable: session-wide (all AIs pause while any draft is pending) or per-participant.

**Summarization checkpoints.** Every 10 turns (configurable), the cheapest AI participant produces a structured-JSON summary (decisions, open questions, key positions, narrative). Summaries are excluded from their own input set to prevent feedback loops. Facilitator can force a checkpoint off-cadence via `/tools/session/summarize_now` (serialized per session).

**Tiered system prompts.** Four prompt tiers (low, mid, high, max) using a delta architecture — each tier appends to the previous without duplication. Total stack is ~1,730 tokens. Canary tokens are injected to detect prompt exfiltration attempts. Designed for cross-model portability (Claude, GPT-4, Llama, Mistral).

**Seven-layer security pipeline.** Sanitization, spotlighting, validation, exfiltration detection, jailbreak detection, prompt defense, log scrubbing. Every input passes through the full pipeline before reaching a provider; every output is validated before being persisted.

## Architecture

| Component | Technology |
|---|---|
| Runtime | Python 3.14.4, FastAPI |
| Database | PostgreSQL 16 via Docker Compose (asyncpg pool) |
| Provider abstraction | LiteLLM >= 1.83.0 (100+ providers) |
| MCP server | FastAPI + SSE, port 8750 |
| Web UI | FastAPI + WebSocket + React SPA (CDN + SRI pins), port 8751 |
| Convergence | sentence-transformers (all-MiniLM-L6-v2, SafeTensors) |
| Auth | bcrypt (tokens) + Fernet (encrypted API keys) + HttpOnly signed cookies |
| Rate limiting | Per-participant, 60 req/min default |
| Migrations | Alembic (11 migrations) |
| Deployment | Single Dockerfile, Docker Compose |
| CI/CD | GitHub Actions → GHCR |
| Pre-commit | 13 hooks (gitleaks, ruff, bandit, 25-line / 5-arg coding-standards lint) |

## Interfaces

Two FastAPI apps run in one process (`src/run_apps.py`):

**MCP server on 8750** — authoritative API surface. ~47 endpoints across session lifecycle (create, pause/resume/archive, start/stop loop, summarize_now, export), participant actions (inject_message, rotate_my_token, add_ai, routing preference), facilitator governance (add/approve/reject/remove participant, create invite, transfer, revoke token, budget, routing, cadence, acceptance mode, complexity classifier, min model tier, review-gate pause scope, bulk-flip routing, approve/reject/edit drafts), proposals (create, vote, resolve, list), and debug export.

**Web UI on 8751** — single-file React SPA served from `frontend/`. HttpOnly+Secure+SameSite=Strict signed cookies carry the bearer. Strict CSP, SRI-pinned CDN dependencies, hardened markdown renderer (neutralizes images, blocks `javascript:` / `data:` / `vbscript:` / `file:` schemes, strips raw HTML, badges invisible Unicode). WebSocket `/ws/{session_id}` delivers a versioned (`v: 1`) event envelope — `state_snapshot`, `message`, `turn_skipped`, `participant_update`, `participant_removed`, `convergence_update`, `review_gate_staged` / `resolved`, `summary_created`, `session_status_changed`, `loop_status`, `audit_entry`, `proposal_*`. Per-IP connection limits, 4401 on unauth, 4403 on foreign session / cross-origin upgrade, 4429 on too-many.

## Governance

The facilitator — the person running the orchestrator — approves participants, sets session configuration, and manages lifecycle. Three roles: facilitator, participant, pending. Pending participants get a redacted holding screen (humans-in-room visible, transcript hidden) until approved. Sessions move through active → paused → archived states. Archive stops the loop, broadcasts a banner to all participants, and auto-generates a final summary. Facilitator role is transferable; the `Facilitator-` display-name prefix follows the role on transfer.

## Security Posture

SACP handles API keys and auth tokens from multiple participants. Security controls target the NIST SP 800-53 moderate baseline for relevant control families (AC, AU, IA, SC, SI). API keys are encrypted at rest (Fernet). Auth tokens are hashed (bcrypt cost 12). All remote connections use TLS in production. No secrets in code, config, or logs — the log scrubber redacts API-key patterns, AWS secrets, emails, phones, SSNs, IBANs, and credit cards.

The codebase enforces a strict secure development pipeline: pre-commit hooks (gitleaks, bandit SAST, ruff, coding-standards lint enforcing 25-line / 5-arg limits), parameterized SQL throughout (SQL injection in display name was tested and held), and a 70+ attack [red-team runbook](docs/red-team-runbook.md) keyed to the seven-layer pipeline.

## Status

**Phase 1 COMPLETE** (2026-04-20) — all scenario tests pass. Core data model, participant auth, turn loop engine, convergence detection, summarization checkpoints, MCP server, AI security pipeline, and rate limiting all shipped.

**Phase 2 COMPLETE** (2026-04-20 through 2026-04-23) — Web UI on port 8751 with 10 user stories delivered. Seven post-release shakedown sweeps (Test06-Web01 through Test06-Web07) have each produced a fix PR landing in `main`:

- Guest landing, invite redeem, cookie-based F5 session restore
- Transfer facilitator (role + display-name prefix + broadcast to both sides)
- Show-my-token (no more rotation cascade)
- Token + cookie re-login after logout works (`/me` no longer rotates)
- Budget 0 = no cap, currency formatted (no float noise), editor "no cap" button
- Session ID visible; Summarize-now, Review-gate-all / Ungate-all, Archive-with-confirm controls
- `addressed_only` routing now actually matches `@<name>`
- Auto-summary on archive (runs before status flip; summarize_now serialized per session)
- Summary feedback loop closed (summaries excluded from own input; watermark advances to max source_turn)
- Reject-participant refresh (new `participant_removed` event; optimistic UI removal)
- Hourly-only budget cap renders correctly
- Review-gate is now one-shot: after draft approval/rejection/edit the AI auto-reverts to its pre-gate routing (cached in ConversationLoop); bulk `set_routing_all_ais` captures per-AI priors in a single transaction
- Removing a human cascades to every AI they sponsored (prevents orphan-AI API spend)
- Rejected pending users see a "Request declined" notice and redirect to the guest landing instead of sitting in limbo

Shakedown-tester documentation lives in [docs/user-guide.md](docs/user-guide.md). The red-team runbook ([docs/red-team-runbook.md](docs/red-team-runbook.md)) has 70+ attacks keyed to the seven-layer pipeline for re-running after any security change. Section 5.4 (multi-turn jailbreak escalation via fictional framing) is a **known weakness** on `gpt-4o-mini`; Haiku held under the same test. Mitigation candidates documented in the runbook, not yet implemented.

**Phase 3 (In Progress — declared 2026-05-05)** — Speckit cycle 012–029 kicked off. Specs implemented to date:

- **012** (audit-fixes) — CRUD audit entries survive participant deletion; admin audit log backfill; two security-event types added.
- **013** (high-traffic mode) — adaptive per-session turn pacing under load; density signal fed to convergence detector; lock-free skip queue for concurrent session bursts.

Specs scaffolded and under active implementation: 014 (dynamic mode assignment), 021 (AI response shaping), 022 (detection event history), 023 (user accounts), 024 (facilitator scratch window), 025 (session-length cap with auto-conclude), 026 (context compression and distillation), 027 (participant standby modes), 029 (human-readable audit log viewer).

**Phase 4 (planned)** — CAPCOM-style routing scope (spec 028), A2A federation, multi-orchestrator linking, hierarchical sub-sessions, OAuth 2.1 with PKCE, local model support (Ollama/vLLM per-participant URL), step-up authorization.
