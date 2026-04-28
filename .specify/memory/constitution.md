<!--
Sync Impact Report
  Version change: 0.5.1 → 0.6.0
  Change type: MINOR — post-deployment hardening + new authoritative references
  Modified principles:
    - §1 Identity: integrated 7 canonical use cases as design test cases
    - §3 Sovereignty: added Topology choice — 7 communication topologies, Phase 1 ships 1–6, MCP-to-MCP is Phase 2+
    - §8 AI-Specific Security: canary token requirement strengthened (multi-canary, no structural format)
    - §8 AI-Specific Security: spotlighting clarified (same-speaker exemption)
    - §12 Validation Rules: added V12 topology compatibility, V13 use case coverage
  Added sections:
    - §14 Change Management (bug-fix and hotfix workflow)
  Removed sections: none
  New authoritative references in §13:
    - sacp-communication-topologies.md (7 participant topologies)
    - sacp-use-cases.md (7 concrete scenarios)
    - sacp-use-cases-and-topologies.md (combined analysis)
    - sacp-system-prompts.md (4-tier delta prompt drafts)
    - testing-runbook.md (operational testing procedures)
  Post-deployment decisions captured (from 2026-04-14 /speckit-clarify session):
    - Default turn timeout raised 60s → 180s (migration 003)
    - Cadence cruise ceiling reduced 300s → 60s (PR #47)
    - Convergence requires ≥3 prior turns for non-zero similarity (PR #47)
  Follow-up TODOs:
    - Implement SSE streaming (spec 006 gap)
    - Restrict CORS from wildcard to LAN+env (spec 006)
    - Harden canary tokens to multi-canary random strings (spec 008)
-->

# SACP Constitution

**Version**: 0.6.0 | **Ratified**: 2026-04-11 | **Last Amended**: 2026-04-14

---

## 1. Identity

SACP is a collaboration protocol, not an agent framework. It is closer to IRC or Matrix than to CrewAI or AutoGen. The orchestrator manages conversation logistics — turn order, context assembly, cost tracking, participant lifecycle — but never owns the AI. Each participant brings their own model, their own API key, their own budget, and their own system prompt extensions. The orchestrator is infrastructure. The participants are sovereign.

The distinction matters for every design decision. Agent frameworks assume a single operator who controls all models, selects tools, defines goals, and pays the bill. SACP assumes multiple independent humans, each with their own AI, collaborating in a shared conversation where no single party has unilateral control over the AI behavior of others.

The concrete scenarios SACP exists to support — distributed software teams reviewing a design across companies, research co-authorship between independent labs, consulting engagements where the consultant brings an AI but the client's data stays in-house, open-source coordination, technical audits, asymmetric expertise pairings, and zero-trust cross-organizational collaboration — are documented in `docs/sacp-use-cases.md`. Every constitutional principle should be testable against those scenarios: a design decision that breaks one of the seven canonical use cases requires explicit justification.

---

## 2. What SACP Is Not

SACP is not a task-execution engine. It does not decompose goals into subtasks, assign them to agents, or evaluate completion. It hosts a conversation.

SACP is not a model router. Each participant chooses their own model and pays for it.

SACP is not a prompt optimization layer. The tiered system prompts establish collaboration norms — they do not attempt to make any participant's AI "better" at its domain.

---

## 3. Sovereignty

Sovereignty is the core architectural principle. Every design decision must preserve these five guarantees:

**API key isolation.** A participant's API key is encrypted at rest and never exposed to other participants, to the facilitator, or in any log output. The orchestrator decrypts only at the moment of provider dispatch and discards the plaintext immediately. Local proxy mode — where the key never leaves the participant's machine — is supported as an alternative. The choice is the participant's. (Implementation: design doc §7.1)

**Model choice independence.** Participants choose their own model and provider. The orchestrator imposes no preference. Sessions may enforce a minimum model tier — participants below the threshold join as observers by default. This is a session-level policy, not a restriction on sovereignty.

**Budget autonomy.** Each participant sets their own budget cap (hourly, daily, per-turn). The orchestrator tracks per-participant usage and cost, enforces the cap, and never pools costs across participants. When a participant hits their budget, their AI stops but their human can still inject messages.

**Prompt privacy.** A participant's custom system prompt content is private to them. Other participants see collaboration metadata (model family, routing mode, domain tags) but not prompt contents. Private annotations are stored client-side, never transmitted to the orchestrator.

**Exit freedom.** Any participant can leave at any time. Their contributions remain in the transcript, but their AI stops receiving turns and their API key is purged.

**Topology choice.** The five sovereignty guarantees above are realized through different communication topologies depending on participant needs. SACP supports seven topologies (catalogued in `docs/sacp-communication-topologies.md`):

1. **Solo + multi-AI** — one human, multiple AIs they own; orchestrator drives the loop
2. **Canonical** — 2+ humans each bring their own AI; orchestrator drives the loop (the default Phase 1 topology)
3. **Asymmetric participation** — some humans observe, others actively contribute their AI
4. **Fully autonomous** — humans drop out; AIs continue conversing on their behalf
5. **Observer + active mix** — pending participants watch live; promoted ones engage
6. **Heterogeneous routing** — different participants on different routing modes (always, observer, addressed_only, etc.)
7. **MCP-to-MCP** — AIs run client-side in participants' desktop clients (Claude Desktop, ChatGPT app); the orchestrator becomes a shared state manager and never makes provider calls. This is the **strongest** sovereignty mode — API keys never leave participants' machines. Tradeoff: when all participants disconnect, the conversation pauses.

Different topologies activate different orchestrator components. Constitutional principles (sovereignty, transparency, human authority) MUST hold across all seven. Phase 1 ships with topologies 1–6 (orchestrator-driven); MCP-to-MCP is Phase 2+.

---

## 4. Principles

These resolve ambiguity when the design doc doesn't have a specific answer.

**4.1 — Transparency over magic.** Every orchestrator decision is logged and visible to participants. Routing logs, convergence logs, and usage logs exist for this reason. Periodic routing summaries let participants tune preferences based on actual data.

**4.2 — Human authority over AI autonomy.** Human interjections always take priority over AI turns via the interrupt queue. No AI response should override, ignore, or deprioritize a human's input.

**4.3 — Graceful degradation over hard failure.** Model failures (timeout, rate limit, content filter, outage) result in skipped turns, not halted sessions. The circuit breaker auto-pauses participants after repeated failures. One-sided conversations (budget exhaustion) trigger cadence reduction and human notification.

**4.4 — Minimum viable context over maximum context.** The context assembly pipeline sends the smallest coherent payload, not the largest the model can accept. Priority order is fixed: interjections → proposals → MVC floor (3 turns) → latest summary → additional history. (Implementation: design doc §4.1)

**4.5 — Session-scoped state.** No cross-session persistence in the core orchestrator. External integrations (Vaire, artifact stores) handle cross-session memory.

**4.6 — Security > Correctness > Readability > Style.** This hierarchy governs every code decision. Higher-priority concerns always win conflicts.

**4.7 — Known limitations are documented, not hidden.** Constraints the design cannot fully solve — prompt injection being the primary example — are documented explicitly. The NIST AI 100-2 taxonomy notes that theoretical impossibility results on adversarial ML mitigations exist. The facilitator approval flow is the ultimate defense.

**4.8 — Defense in depth, not silver bullets.** No single defense solves prompt injection, exfiltration, or cross-model poisoning. SACP uses six coordinated defense layers: network, application, data, AI/ML, operational, and governance. Every security decision must identify its layer and whether adjacent layers provide backup. (Framework: attack surface analysis §14)

---

## 5. Governance

The facilitator is the person who runs the orchestrator. They are not a superuser — they cannot edit messages, read API keys, or override routing preferences. Their powers are bounded to session lifecycle and participant management:

- Create and configure sessions (topic, cadence, convergence threshold, adversarial rotation interval, complexity classifier mode, min model tier, acceptance mode, auto-archive/auto-delete).
- Generate invite links (single-use or multi-use, configurable expiry). Auto-approve mode available for trusted contexts.
- Approve or reject participants. Pause, resume, archive, or delete sessions.
- Remove participants (logged to admin audit log).
- Rotate or revoke auth tokens (forcing immediate disconnection).
- Transfer the facilitator role to another participant.
- Override any open proposal (logged to admin audit log).
- Export sessions (markdown, JSON, Vaire bulk import).
- Review and act on security flags (jailbreak detection, prompt extraction attempts, tool call violations).

The facilitator cannot impersonate a participant, send messages as another's AI, modify another's system prompt or routing preference, or read another's API key. Every facilitator action is recorded in the admin audit log.

**Three participant roles:** facilitator (one per session, transferable, full admin tools), participant (full collaboration access, no admin), pending (read-only transcript, no injection, AI not in loop — lets potential collaborators see the session before committing their API key).

(Full tool definitions: design doc §4.4)

---

## 6. Technical Constraints

Non-negotiable implementation boundaries.

**6.1 — Runtime:** Python 3.11+, FastAPI.

**6.2 — Database:** PostgreSQL 16, asyncpg with connection pooling, LISTEN/NOTIFY, Alembic migrations. Append-only log tables restricted to INSERT and SELECT only for the application database role. Statement and idle transaction timeouts configured to prevent resource exhaustion.

**6.3 — Provider abstraction:** LiteLLM, pinned to a verified version (v1.83.0+ due to confirmed supply chain compromise in 1.82.7–1.82.8). Runs in a network-restricted container with egress limited to approved provider endpoints. Direct SDK calls (anthropic, openai, httpx) as fallbacks only. (Supply chain details: attack surface analysis §10)

**6.4 — MCP server:** Python MCP SDK, SSE transport, port 8750. Sessions bound to authenticated participant and client IP. Concurrent connections capped globally and per-IP. (Hardening: design doc §7.5, attack surface analysis §8)

**6.5 — Auth (Phase 1):** Static tokens, bcrypt hashing, configurable expiry (default 30 days), rotation. Fernet encryption for API keys at rest. (Key management: design doc §7.1)

**6.6 — Auth (Phase 3):** OAuth 2.1 with PKCE (S256), authlib, python-jose. Replaces static tokens entirely. Step-up authorization for destructive facilitator actions. (MCP auth evolution: design doc §6.7)

**6.7 — Convergence detection:** sentence-transformers (all-MiniLM-L6-v2), numpy. SafeTensors format exclusively — no pickle deserialization. Multi-signal detection (embedding similarity + lexical overlap + nonsense detection), not embeddings alone. (Adversarial defense: attack surface analysis §9)

**6.8 — Container:** Docker Compose, FastAPI + PostgreSQL 16. Alpine-based image. PostgreSQL co-located on the same Docker network. LiteLLM network-isolated. No Kubernetes, Helm, or cloud-managed services in Phase 1.

**6.9 — Tree-structured messages from day one.** Every message has `parent_turn` and `branch_id`. Branching UI is Phase 3 but the data model supports it from the first migration.

**6.10 — Coding standards:** 25-line function cap, 5-argument positional limit, type hints on all signatures, caller-above-callee ordering. Pre-commit hooks (gitleaks → ruff → lint_code_standards.py). No `--no-verify`. (Rules: coding-standards.md, pipeline: dod-secure-dev.md)

**6.11 — Structured JSON logging.** Log scrubbing before emission, not post-processing. Credential patterns redacted. Python `excepthook` overridden to prevent key material in tracebacks. (Scrubbing patterns: design doc §7.5)

---

## 7. Data Security

SACP handles credentials and conversation data across trust boundaries between independent participants. The security model covers data at rest, data in transit, key management, participant data isolation, and data retention.

**Requirements are specified in `sacp-data-security-policy.md`, which is the authoritative reference for:**

- Three-tier data-at-rest classification (secrets → sensitive metadata → conversation content) with protection requirements per tier.
- Data-in-transit encryption requirements for all five network paths (participant↔orchestrator, orchestrator↔provider, orchestrator↔PostgreSQL, orchestrator↔external MCP, remote access).
- Key management lifecycle (deployment options, first-run behavior, rotation via `sacp-rotate-key` CLI, compromise response procedure).
- Participant data isolation matrix (what's shared, what's private, what's facilitator-only) with application-layer enforcement requirement.
- Data retention and disposal procedures (participant departure, session deletion, automatic lifecycle, database backups).
- Shared project data model (Phase 1 limitations, Phase 2–3 artifact store).
- Conversation transparency and access rights (immutable history, four operational log categories, log integrity enforcement, export formats and access scoping).

**Constitutional data security principles** (these override any implementation detail that conflicts):

- Secrets are never stored in plaintext, never logged, never exposed to other participants.
- Data in transit across network boundaries is encrypted (TLS 1.2+). Internal Docker bridge traffic is considered trusted.
- When data is deleted, it is deleted — not soft-deleted, not orphaned. Session deletion is atomic and irreversible.
- Participant data isolation is enforced at the application layer, not just the database. Every API response is filtered by caller identity.
- Operational logs are append-only. The application database role cannot UPDATE or DELETE log table rows.
- Every participant can export the conversation history and their own usage data for any session they participated in.

---

## 8. AI-Specific Security

SACP's defining security challenge: one AI's output is another AI's input. The conversation itself is the injection surface. The attack surface analysis catalogs 13 attack vector families. The NIST AI 100-2 taxonomy maps six categories directly onto SACP's architecture.

**Constitutional AI security requirements** (implementation details in design doc §7.6 and attack surface analysis §1–13):

- **Trust-tiered content model.** All content is classified into three trust tiers (system instructions → human interjections → AI responses) with structural isolation between tiers. No content from a lower tier is ever promoted to a higher tier. Tool results inherit the trust tier of their trigger source.

- **Structural boundary markers.** The context assembly pipeline uses XML-style delimiters (`<sacp:system>`, `<sacp:human>`, `<sacp:ai>`, `<sacp:tool>`, `<sacp:context>`) between trust levels. These are payload-only markers, not displayed to users.

- **Inter-agent spotlighting.** AI responses from OTHER participants are spotlighted (datamarked) before inclusion in the current AI's context to disrupt instruction injection propagation. Same-speaker content (an AI reading its own prior output) is exempt — there is no trust boundary to enforce when reading your own output, and spotlighting own-history bloats context without security benefit.

- **Context sanitization.** All messages are preprocessed to strip known injection patterns (ChatML tokens, role markers, override phrases, invisible Unicode) before entering conversation history.

- **Cross-model safety profiling.** The orchestrator maintains per-model safety tiers. Outputs from low-safety and untrusted models pass through additional validation. Sessions can enforce minimum model tiers for participation.

- **Multi-layer output validation.** Every AI response passes through a validation pipeline (pattern matching → semantic analysis → LLM-as-judge for flagged content) before entering conversation history. Blocked responses are held for facilitator review, never silently passed through.

- **Jailbreak propagation detection.** Behavioral drift heuristics flag responses that deviate from established patterns. Flagged responses are held, not committed.

- **System prompt extraction defense.** Prompts are designed assuming they will be extracted — they never contain secrets. Multiple high-entropy canary tokens (minimum three per prompt, placed at distinct positions — start, middle, end) detect selective extraction attempts. Canary tokens MUST NOT use structural formats (no HTML comments, no XML tags) that attackers can prime models to avoid reproducing. Fragment scanning (25+ word overlap with any participant's system prompt) catches paraphrased extraction.

- **Role-based tool call scoping.** Tool availability is restricted by participant role, not just model capability. Facilitator-only tools are never exposed to non-facilitators. All tool parameters are validated against an SSRF blocklist. External tool calls are size-capped and restricted to a registered allowlist with hashed definitions.

- **Adversarial embedding defense.** Convergence detection uses multiple signals, not embeddings alone. Embedding vectors are never exposed through any API endpoint.

- **Data exfiltration defense.** Markdown image syntax and HTML `src` attributes are stripped from AI responses. URL-based exfiltration patterns are flagged. Output anomaly detection compares against behavioral baselines.

---

## 9. Security Boundaries

General security requirements beyond data and AI-specific concerns.

- **Secrets never in code, config, or logs.** Environment variables or secrets management only. Log scrubbing is mandatory on all output paths including tracebacks.
- **Input validation on all external boundaries.** Every MCP tool input and API parameter is validated before processing. (Specific constraints: design doc §7.5)
- **Response size enforcement.** Hard byte limit on AI responses before database storage, independent of `max_tokens_per_turn`.
- **Rate limiting.** Per-participant rate limits on all MCP tool calls, independent of budget controls. (Defaults: design doc §7.5)
- **Origin validation.** Origin header checked on all MCP SSE and WebSocket connections to prevent DNS rebinding.
- **CORS and CSP.** Restrictive CORS on Web UI. CSP prevents inline script execution.
- **MCP SSE hardening.** Sessions bound to client IP. Connection limits enforced. Tool description hashing detects rug-pull attacks. (Details: attack surface analysis §8)
- **DoS multiplication awareness.** Hard timeouts on all LiteLLM calls. CPU-bound operations offloaded from the async event loop. Per-participant budgets enforced at the orchestrator level. (Details: attack surface analysis §12)
- **Dependency security.** All dependencies pinned with hash verification. SBOM maintained. LiteLLM network-isolated. ML models loaded in SafeTensors only. CI runs `pip-audit` and `safety`. (LiteLLM supply chain history: attack surface analysis §10)
- **Banned functions.** No `eval()`, `exec()`, `pickle.loads()` on untrusted data, or `subprocess` with `shell=True`. (Full list: coding-standards.md)

---

## 10. Phase Boundaries

Each phase is a complete, usable system. No phase depends on a future phase to function.

**Phase 1 (MVP):** Two participants, one facilitator. Static token auth. LiteLLM bridge (network-isolated). 4-tier delta-only system prompts with canary tokens. Serialized turn loop with all 8 routing modes, complexity classifier (pattern-matching), interrupt queue, multi-signal convergence detection, adaptive cadence, adversarial rotation, per-turn timeouts. Context assembly with 5-priority token budget and summarization checkpoints. `[NEED:]` tool proxy with allowlist and SSRF protection. Full AI security pipeline (spotlighting, sanitization, safety profiling, multi-layer output validation, jailbreak detection, prompt extraction defense, role-based tool scoping, exfiltration defense, trust-tiered content model). Error detection with retry and circuit breaker. TLS, rate limiting, input validation, response size enforcement, origin validation, MCP SSE binding, CORS/CSP, log scrubbing. Append-only logs with restricted DB permissions. Admin audit log. Export (markdown, JSON, Vaire). One-sided conversation detection. Docker Compose. SafeTensors-only. SBOM. No web UI. No artifact store.

**Phase 2:** Web UI (port 8751) with streaming, review-gate UI, invite/onboarding. Session archiving, export (UI), forking. Multi-project support. Decision/proposal workflow. Participant-facing audit log subset. Artifact store (blob KV). Per-participant context optimization. Envelope encryption migration.

**Phase 3:** 3–5 participants. Branching and rollback with UI. Sub-sessions with conclusion merging. Vaire integration. Relevance-based routing, broadcast mode. Ollama/vLLM local model support. OAuth 2.1 with PKCE replaces static tokens. Step-up authorization. Artifact store enhancements. Git-backed decision tracking.

**Phase 4:** A2A federation. Agent Card discovery. Hierarchical sub-sessions. Data retention policies. Formal protocol spec. Evaluate Inter-Agent Trust Protocol for multi-sovereign trust.

A feature spec that references capabilities from a later phase is out of scope and must be flagged. Phase boundaries are hard scope limits.

---

## 11. Regulatory Awareness

The EU AI Act's high-risk AI obligations take effect August 2, 2026 (possible delay to December 2, 2027 per Digital Omnibus proposal; trilogue ongoing as of April 2026). Full compliance assessment is deferred to Phase 4, but Phase 1 design decisions (append-only audit logs, facilitator accountability, participant data isolation, export) must not create obstacles to future compliance.

---

## 12. Validation Rules

Every feature spec must pass these checks. Failure requires revision before implementation.

**V1 — Sovereignty preserved.** API key isolation, model choice independence, budget autonomy, prompt privacy, and exit freedom are all maintained.

**V2 — No cross-phase leakage.** The spec does not require capabilities from a later phase.

**V3 — Security hierarchy respected.** No trade-off prioritizes readability or style over security or correctness.

**V4 — Facilitator powers bounded.** No facilitator capability beyond those listed in section 5.

**V5 — Transparency maintained.** No orchestrator behavior is unlogged or invisible to participants. No restriction on conversation history or log access beyond what `sacp-data-security-policy.md` §5 permits.

**V6 — Graceful degradation.** No failure mode halts the session.

**V7 — Coding standards met.** 25/5 limits, type hints, pre-commit hooks, banned functions.

**V8 — Data security enforced.** Secrets, metadata, and content comply with the appropriate tier. Transit encryption per policy. Isolation boundaries respected. Retention/disposal requirements met. (Reference: `sacp-data-security-policy.md`)

**V9 — Log integrity preserved.** Operational log writes are append-only. Application DB role has INSERT and SELECT only on log tables.

**V10 — AI security pipeline enforced.** Content entering another AI's context applies trust tiers, boundary markers, spotlighting, sanitization, and output validation. Tool calls are role-scoped. (Reference: section 8, design doc §7.6, attack surface analysis §1–13)

**V11 — Supply chain controls enforced.** New dependencies pinned with hash verification and reviewed against OSINT sources. ML models loaded in SafeTensors only.

**V12 — Topology compatibility verified.** Every feature spec MUST identify which of the seven topologies (`docs/sacp-communication-topologies.md`) it applies to. Features that work in topology 1–6 (orchestrator-driven) but break topology 7 (MCP-to-MCP) MUST flag the limitation explicitly in their spec. A feature that silently assumes orchestrator-driven AI dispatch is incomplete.

**V13 — Use case coverage acknowledged.** Every feature spec MUST reference at least one of the seven use cases (`docs/sacp-use-cases.md`) it primarily serves, OR explicitly justify why the feature is foundational/cross-cutting. This prevents accidental drift toward features that look reasonable in isolation but don't serve any of the canonical scenarios.

---

## 13. Authoritative References

### Design & Architecture

| Document | Role | Scope |
|---|---|---|
| `docs/sacp-design.md` | Design specification | Architecture, schema, components, security implementation (§7.1–7.6), governance, lifecycle, data flows, deployment |
| `docs/sacp-data-security-policy.md` | Data security policy | Data classification, isolation matrix, retention, key management, export access, log integrity, shared data model |
| `docs/sacp-system-prompts.md` | System prompt drafts | 4-tier delta-only prompt content (low/mid/high/max), canary token placement, custom prompt composition |
| `docs/sacp-communication-topologies.md` | Topology analysis | Seven participant topologies (solo+multi-AI, canonical, asymmetric, autonomous, MCP-to-MCP, etc.), active orchestrator components per topology |
| `docs/sacp-use-cases.md` | Use case scenarios | Seven concrete scenarios demonstrating where SACP fills gaps existing tools cannot cover |
| `docs/sacp-use-cases-and-topologies.md` | Combined analysis | Maps each use case to its communication topology with sequence diagrams and active component tables |

### Security Analysis

| Document | Role | Scope |
|---|---|---|
| `docs/AI_attack_surface_analysis_for_SACP_orchestrator.md` | AI security analysis | 13 attack vectors, severity ratings, mitigations, code patterns, standards mappings, six-layer defense framework |
| `docs/eight-hard-problems.md` | Research report | Cross-provider engineering challenges, informs patterns, does not override design doc |

### Development & Operations

| Document | Role | Scope |
|---|---|---|
| `references/coding-standards.md` | Code rules | 25/5 limits, type hints, banned functions, baseline mode |
| `references/dod-secure-dev.md` | Dev pipeline | Pre-commit, CI, periodic review layers |
| `.pre-commit-config.yaml` | Hook chain | gitleaks → ruff → lint_code_standards.py |
| `docs/testing-runbook.md` | Testing procedures | Operational testing workflows, integration test procedures |

### Regulatory & Frameworks

| Document | Role | Scope |
|---|---|---|
| `references/csf-2.0-framework.md` | NIST CSF 2.0 | Governance framework for security decisions |
| `references/800-53B-baselines.md` | NIST SP 800-53B | Control baselines (moderate target) |
| `references/ai-100-2-aml-taxonomy.md` | NIST AI 100-2 | Adversarial ML threat taxonomy |
| `references/sp-800-181-nice.md` | NIST NICE Framework | Workforce competency model |
| `references/osint-sources.md` | Threat intel | Dependency and infrastructure vulnerability monitoring |

---

## 14. Change Management

Not every code change deserves a full Speckit feature workflow. Forcing spec ceremony on a one-line regex fix is waste; shipping a new feature without one is sloppy. This section defines which category a change belongs to and what paperwork it requires.

### 14.1 — Feature work (full Speckit workflow)

Any change that adds new user-visible capability, a new entity, a new endpoint, or alters a core algorithm. Goes through:

1. `/speckit-git-feature` — creates numbered branch (e.g., `010-web-ui`) and spec directory
2. `/speckit-specify` — writes `spec.md` with user stories, FRs, acceptance scenarios, success criteria
3. `/speckit-clarify` — resolves ambiguities before implementation begins
4. `/speckit-plan` — writes `plan.md` with Technical Context fields (Language/Version, Primary Dependencies, Storage, Project Type)
5. `/speckit-tasks` — breaks plan into trackable tasks.md items
6. Implementation + tests
7. Mark tasks `[X]` as completed in `tasks.md`
8. Run `update-context` so CLAUDE.md reflects the new tech
9. PR review and merge

The numbered branch is required. The branch naming convention `NNN-feature-name` is enforced by `speckit.git.validate`.

### 14.2 — Bug fixes (lightweight workflow)

Changes that restore correctness of existing behavior without adding capability. Examples: regex widening, timeout tuning, race condition fix, test infrastructure repair. Workflow:

1. Branch naming: `fix/<short-slug>` (not numbered — bug fixes don't claim a feature slot)
2. No new spec — the feature spec already exists
3. **Required**: if the fix changes observable behavior (default values, thresholds, error semantics), update the affected feature's `spec.md` AND add a `## Clarifications` entry noting the change and the PR number
4. **Required**: update `tasks.md` to reflect any new behavior (new tasks, all marked `[X]` since they ship in the same PR)
5. PR review and merge

Example from this project: PRs #45-47 changed default turn timeout (60→180s), cadence ceiling (300→60s), and convergence min-window (1→3). All three touched code AND updated the affected feature specs retroactively via `/speckit-clarify` on 2026-04-14.

### 14.3 — Hotfixes (security / production incident)

A bug fix that must ship before a full PR review cycle. Same as §14.2 workflow, but with these additions:

1. Branch naming: `hotfix/<short-slug>`
2. Direct merge allowed after minimum-viable review (security: at least one additional reviewer; production incident: facilitator or on-call owner)
3. Spec update and audit log entry are still required — may be done in a follow-up PR within 48 hours of the hotfix landing

### 14.4 — Documentation-only changes

Spec clarifications, README updates, adding reference docs to this constitution, correcting typos in `docs/`. Workflow:

1. Branch naming: `docs/<short-slug>`
2. No code changes allowed on this branch (enforced by reviewer)
3. PR review for content accuracy, not behavioral correctness

### 14.5 — Constitutional amendments

Changes to this document. Require explicit version bump:

- **PATCH** (0.5.1 → 0.5.2): metadata only, typos, reference additions without semantic change
- **MINOR** (0.5.x → 0.6.0): new principle, new validation rule, new section, clarification of existing principle that tightens or relaxes it
- **MAJOR** (0.x → 1.0): removal of a principle, scope-expanding change, Phase boundary movement

Every amendment updates the Sync Impact Report block at the top of this file. Every amendment is reviewed by the facilitator before merge.

### 14.6 — The "no ceremony without value" principle

When in doubt, pick the lightest workflow that captures the decision in a way future-you can audit. A two-line regex fix needing a full spec is bureaucracy; a new multi-agent routing mode shipping without a spec is debt. The test is: **will a future developer trying to understand this change find enough to reconstruct the reasoning?** If yes, the workflow is right-sized. If no, escalate.
