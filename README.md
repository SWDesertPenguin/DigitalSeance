# Digital Seance

**Sovereign AI Collaboration Protocol (SACP)**

SACP is a multi-sovereign orchestrator that enables persistent, autonomous AI-to-AI conversation with human drop-in collaboration. Each participant brings their own AI, API key, model choice, and budget. The orchestrator manages the conversation loop, turn routing, cost tracking, and human interjection while preserving participant sovereignty.

This is a collaboration protocol — closer to IRC or Matrix than to CrewAI or AutoGen. No single operator controls all the AIs. No shared API key. No centralized billing.

## What Problem Does This Solve?

Single-operator agent frameworks (CrewAI, AutoGen, LangGraph) let one person spin up multiple AI agents under one API key, one config, one budget. When the task finishes, the system shuts down.

Shared-AI collaboration tools (Copilot Cowork, Slack AI) give multiple humans access to a single AI. Many humans, one AI.

Neither handles the case where multiple independent people — each with their own AI, their own context, their own project knowledge — need their AIs to work together on a shared project. Open-source contributors, co-authors, research teams, consulting engagements — any distributed collaboration where participants have been building context separately and need to synchronize without copy-paste.

SACP fills that gap. Multiple humans, multiple AIs, persistent conversation, distributed cost.

## How It Works

A facilitator runs the orchestrator as a Docker container. Participants join via invite codes, register their AI provider and model, and set a routing preference that controls their level of engagement — from responding every turn down to only responding when a human speaks.

The orchestrator runs a serialized conversation loop: select the next participant, build a context window from recent history and summaries, call their AI provider through LiteLLM, validate the response against a seven-layer security pipeline, log costs, check for convergence, and repeat. When all humans walk away, the AIs keep working. Humans drop in through MCP clients (Claude Desktop, Claude Code) or the Web UI, inject messages, steer direction, and leave.

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

## License

Code is licensed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE) for details.

Documentation is licensed under Creative Commons Attribution 4.0 International (CC BY 4.0). See [LICENSE-DOCS](LICENSE-DOCS) for details.
