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

**Convergence detection.** Embedding similarity tracked over a sliding window. When similarity crosses a configurable threshold, the orchestrator injects a divergence prompt; sustained convergence pauses the loop and escalates to humans.

**Adaptive cadence.** Turn pacing adjusts based on content quality. Productive conversation runs faster. Repetitive conversation slows down. Human interjection temporarily spikes responsiveness. Repeated skips back off exponentially when the only viable AI just spoke.

**Review gate.** Participants can route through a facilitator approval queue. Drafts are staged, not written to the transcript; the facilitator approves / rejects / edits before anything becomes canonical. Pause scope is facilitator-configurable: session-wide (all AIs pause while any draft is pending) or per-participant.

**Summarization checkpoints.** On a configurable cadence, the cheapest AI participant produces a structured summary covering decisions, open questions, key positions, and narrative. Summaries are excluded from their own input set to prevent feedback loops. Facilitator can force a checkpoint off-cadence via the MCP API.

**Tiered system prompts.** Multiple prompt tiers using a delta architecture — each tier appends to the previous without duplication. Exfiltration detection is embedded in the prompt stack. Designed for cross-model portability (Claude, GPT-4, Llama, Mistral).

**Seven-layer security pipeline.** Sanitization, spotlighting, validation, exfiltration detection, jailbreak detection, prompt defense, log scrubbing. Every input passes through the full pipeline before reaching a provider; every output is validated before being persisted.

## Architecture

| Component | Technology |
|---|---|
| Runtime | Python 3.14.4, FastAPI |
| Database | PostgreSQL 16 via Docker Compose (asyncpg pool) |
| Provider abstraction | LiteLLM (100+ providers) |
| MCP server | FastAPI + SSE, port 8750 |
| Web UI | FastAPI + WebSocket + React SPA (CDN + SRI pins), port 8751 |
| Convergence | sentence-transformers (CPU-safe, SafeTensors) |
| Auth | bcrypt (tokens) + Fernet (encrypted API keys) + HttpOnly signed cookies (Secure + SameSite=Strict) |
| Rate limiting | Per-participant |
| Migrations | Alembic (11 migrations) |
| Deployment | Single Dockerfile, Docker Compose |
| CI/CD | GitHub Actions → GHCR |
| Pre-commit | gitleaks, ruff, bandit, coding-standards lint |

## Interfaces

Two FastAPI apps run in one process:

**MCP server on 8750** — authoritative API surface covering session lifecycle, participant actions, facilitator governance, proposals, and debug export. Intended for MCP clients (Claude Desktop, Claude Code).

**Web UI on 8751** — single-file React SPA. HttpOnly signed cookies carry the bearer. Strict CSP, SRI-pinned CDN dependencies, hardened markdown renderer. Real-time updates delivered over WebSocket. Per-IP connection limits enforced.

## Governance

The facilitator — the person running the orchestrator — approves participants, sets session configuration, and manages lifecycle. Three roles: facilitator, participant, pending. Pending participants get a redacted holding screen (humans-in-room visible, transcript hidden) until approved. Sessions move through active → paused → archived states. Archive stops the loop, broadcasts a banner to all participants, and auto-generates a final summary. Facilitator role is transferable; the `Facilitator-` display-name prefix follows the role on transfer.

## Security Posture

SACP handles API keys and auth tokens from multiple participants. Security controls target the NIST SP 800-53 moderate baseline for relevant control families (AC, AU, IA, SC, SI). API keys are encrypted at rest. Auth tokens are hashed. All remote connections use TLS in production. No secrets in code, config, or logs — the log scrubber redacts credentials, PII, and payment data patterns.

The codebase enforces a strict secure development pipeline: pre-commit hooks (gitleaks, bandit SAST, ruff, coding-standards lint), parameterized SQL throughout, and a comprehensive red-team runbook keyed to the seven-layer pipeline.

## Status

**Phase 1 COMPLETE** — core engine shipped: data model, participant auth, turn loop, convergence detection, summarization, MCP server, AI security pipeline, and rate limiting.

**Phase 2 COMPLETE** — Web UI shipped with full session lifecycle, participant governance, and facilitator controls. Post-release shakedown sweeps addressed UX and correctness issues.

**Phase 3 (In Progress)** — advanced features under active development: audit hardening, high-traffic scalability, dynamic routing, AI response shaping, user accounts, session-length caps, context compression, participant standby modes, and a human-readable audit log viewer.

**Phase 4 (planned)** — federation, multi-orchestrator linking, OAuth 2.1, local model support (Ollama/vLLM), and step-up authorization.
