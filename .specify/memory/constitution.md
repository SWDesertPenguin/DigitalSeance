<!--
Sync Impact Report (most recent first)

  Version change: 0.7.6 → 0.8.0 (2026-05-05)
  Change type: MINOR — Phase 3 declared started; Phase 2 audit window marked closed
  Modified principles:
    - §10 Phase Boundaries: Phase 2 line gains "audit window closed 2026-05-04"
      and the audit-window summary (419 shipped / 55 residual / 0 unchecked).
      Phase 3 line gains "declared started 2026-05-05" and references the
      already-drafted specs 013 (high-traffic-mode / broadcast) and 014
      (dynamic mode assignment / signal-driven controller). Phase 3 lifts
      both specs' "remains Draft until facilitator declares Phase 3" gate;
      tasks and implementation now proceed per Constitution §14.1.
  Added sections: none
  Removed sections: none
  Cross-doc updates:
    - specs/013-high-traffic-mode/spec.md: Phase 3 declaration noted in
      Status section; "remains Draft until that declaration" gate marked
      satisfied. Spec stays Draft until tasks land and implementation
      reaches Implemented status.
    - specs/014-dynamic-mode-assignment/spec.md: Phase 3 declaration
      noted; the secondary gate ("spec 013 reaches Status: Implemented")
      remains active until 013 ships.

  Version change: 0.7.5 → 0.7.6 (2026-05-02)
  Change type: PATCH — voice-mediated participants explicitly out of scope at all phases
  Modified principles:
    - §2 What SACP Is Not: new exclusion paragraph for voice-mediated
      participants (orchestrator-side wire is text; voice transport,
      raw-audio MCP tools, and acoustic protocol negotiation excluded
      at any phase)
    - §10 Phase Boundaries: Phase 3+ deferred-decisions note added
      listing the six architectural commitments (STT canonicalization,
      TTS re-synthesis from canonical text, refusal of in-band
      protocol negotiation, voice participant trust tier, no raw-audio
      federation, voice participant disclosure) that would govern any
      future voice-participant admission
  Added sections: none
  Removed sections: none

  Version change: 0.7.4 → 0.7.5 (2026-05-01)
  Change type: PATCH — api-versioning.md added to §13 reference registry
  Modified principles: none
  Added §13 references:
    - docs/api-versioning.md (API versioning and deprecation policy; Phase G audit deliverable)
  Removed sections: none

  Version change: 0.7.3 → 0.7.4 (2026-05-01)
  Change type: PATCH — constitution-adherence audit sweep; ADR 0001 materialised; spec 012 topology section added
  Modified principles: none
  Added references:
    - docs/adr/0001-fire-and-forget-summarization.md (first ADR; listed in §13 since v0.7.2, now created)
  Added sections: none
  Removed sections: none
  Audit findings (fix/constitution-adherence):
    - §3 topology: 11/12 specs compliant; spec 012 was missing — resolved in this PR
    - §8 AI-specific security: all relevant specs reference §8 or its downstream specs (007, 008) — compliant
    - §9 security boundaries: 002, 006, 009, 011 document security boundaries — compliant
    - §10 classifier scope: 003 §FR-017 aligns with §10 pattern-matching-only constraint — compliant
    - §11 line/arg limits: spot-checked; no violations in Phase B amendments — compliant
    - §13 doc references: docs/adr/0001 was listed but not created — resolved; all other §13 docs exist
    - §14 Phase boundaries: Phase 2→3 boundary documented in §10 and §14.7; gating active — compliant
    - V14 coverage: 003/007 hot paths have per-stage timing (PRs #172/#186/#209) — compliant
    - V15 coverage: 007 §FR-013 fail-closed, 008 canary fail-closed — compliant
    - V16 coverage: 13 validators in src/config/validators.py cover all consumed vars; SACP_CONVERGENCE_THRESHOLD + SACP_TURN_TIMEOUT_SECONDS deferred to Phase E (documented gaps, not blocking)
    - Amendment traceability: §4.9 resolution reflected in 007 §FR-005 and 012 Clarifications — compliant
    - Phase 3 readiness gate: §14.7 gating active; no Phase 3 deliverables declared yet (deferred to Phase H closeout)

  Version change: 0.7.2 → 0.7.3 (2026-05-01)
  Change type: PATCH — §4.9 placeholder qualifier removed; approach (b) recorded
  Modified principles:
    - §4.9 Secure by design: "under architectural review" text replaced with
      the chosen resolution (approach (b)) and its implementation surface
  Added sections: none
  Removed sections: none

  Version change: 0.7.1 → 0.7.2 (2026-04-30)
  Change type: MINOR — new §14.8 spec versioning convention + 3 new §13 references
  Modified principles: none
  Added sections:
    - §14.8 Spec versioning convention (PATCH/MINOR/MAJOR analog for spec.md amendments)
  Added §13 references:
    - docs/pattern-list-update-workflow.md (007 §FR-017 incident → PR cycle)
    - docs/threat-model-review-process.md (per-Phase-boundary cadence + 4 triggers)
    - docs/adr/ (MADR 4.0 architectural decision records; first ADR retrospectively documents Phase 2's fire-and-forget summarization choice)
  Removed sections: none

  Version change: 0.7.0 → 0.7.1 (2026-04-30)
  Change type: PATCH — reference addition without semantic change
  Modified principles: none
  Added §13 references: docs/env-vars.md (env-var catalog backing V16
    startup validators per spec 012 FR-005). Companion to
    src/config/validators.py landed in the same PR (012 US2).
  Removed sections: none

  Version change: 0.6.0 → 0.7.0
  Change type: MINOR — Phase 2 retrospective + new principle (placeholder) + new validation rules + new change-management category + drift corrections
  Modified principles:
    - §3 Sovereignty: topology line "MCP-to-MCP is Phase 2+" corrected to "Phase 3+" (Phase 2 shipped without topology 7 per spec 011 Out of Scope)
    - §6.8 Container: "Alpine-based image" corrected to Debian slim-bookworm (deliberate choice for glibc / wheel ABI compatibility — torch, sentence-transformers)
    - §8 AI-Specific Security: cross-model safety profiling explicitly deferred (listed as constitutional requirement but not implemented in Phase 1+2; trigger added)
    - §9 Security Boundaries: tool description hashing explicitly deferred (same shape as cross-model safety profiling)
    - §10 Phase Boundaries: Phase 2 description rewritten as retrospective of what actually shipped vs. what deferred to Phase 3
  Added sections:
    - §4.9 Secure by design (placeholder — implementation under architectural review per AUDIT_PLAN cross-cutting item)
    - §12 V14 Performance budgets specified + instrumented
    - §12 V15 Security pipeline fail-closed
    - §12 V16 Configuration validation at startup
    - §14.7 Audit work category
  Removed sections: none
  New authoritative references in §13:
    - docs/red-team-runbook.md (operational red-team workflow + incident catalog)
  Phase 2 decisions captured (post-2026-04-29 /speckit-constitution session):
    - 11-spec security-audit sweep landed (PR #157, 439 findings + 14 code drifts)
    - Tier 1-3 quality checklists landed (PRs #159, #161)
    - Trivy CVE-2025-47273 setuptools fix landed in three rounds (PRs #158, #160, #162); pattern documented for future multi-stage Docker COPY work
    - Performance audit + spec amendments landed (PR #163) — added FR-030/031/032 to 003, FR-018/019/020 to 006, FR-020/021/022/023 to 007, FR-011/012/013/014 to 008, FR-011/012/013/014 to 009; codifies stage timings, compound-retry caps, subscriber caps, request-id propagation, per-layer budgets, memoization contracts, ReDoS guard, 429-rate metrics
  Follow-up TODOs (closed from previous version):
    - ✓ SSE streaming implemented (spec 006)
    - ✓ CORS restricted from wildcard to LAN+env (spec 006)
    - ✓ Canary tokens hardened to multi-canary random base32 (spec 008)
  Follow-up TODOs (new this version):
    - V14 perf-budget contracts: PR #163 codified the spec contracts; instrumentation implementation outstanding (per-stage timing capture, memoization caches, retention purge job, subscriber-cap enforcement, request-id middleware, benchmark + CI regression gate).
    - V16 env-var validation: AUDIT_PLAN batch 5 config-validation audit will catalog every SACP_* var with type/range/fail-closed semantics.
    - Constitution adherence audit (AUDIT_PLAN batch 5): full review may surface additional amendments; this v0.7.0 is interim.
-->

# SACP Constitution

**Version**: 0.7.6 | **Ratified**: 2026-04-11 | **Last Amended**: 2026-05-02

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

Voice-mediated participants are out of scope. Participants communicate as text. The bridge layer translates between participant-side AI providers and the orchestrator, but the orchestrator-side wire is text. Voice transport, raw-audio MCP tools, and acoustic protocol negotiation are not part of SACP at any phase.

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

Different topologies activate different orchestrator components. Constitutional principles (sovereignty, transparency, human authority) MUST hold across all seven. Phase 1+2 ship with topologies 1–6 (orchestrator-driven); MCP-to-MCP is Phase 3+ (deferred from earlier "Phase 2+" framing — Phase 2 shipped without topology 7 per spec 011 Out of Scope).

---

## 4. Principles

These resolve ambiguity when the design doc doesn't have a specific answer.

**4.1 — Transparency over magic.** Every orchestrator decision is logged and visible to participants. Routing logs, convergence logs, and usage logs exist for this reason. Periodic routing summaries let participants tune preferences based on actual data.

**4.2 — Human authority over AI autonomy.** Human interjections always take priority over AI turns via the interrupt queue. No AI response should override, ignore, or deprioritize a human's input.

**4.3 — Graceful degradation over hard failure.** Model failures (timeout, rate limit, content filter, outage) result in skipped turns, not halted sessions. The circuit breaker auto-pauses participants after repeated failures. One-sided conversations (budget exhaustion) trigger cadence reduction and human notification.

**4.4 — Minimum viable context over maximum context.** The context assembly pipeline sends the smallest coherent payload, not the largest the model can accept. Priority order is fixed: interjections → proposals → MVC floor (3 turns) → latest summary → additional history. (Implementation: design doc §4.1)

**4.5 — Session-scoped state.** No cross-session persistence in the core orchestrator. External integrations (memory stores, artifact stores) handle cross-session memory.

**4.6 — Security > Correctness > Readability > Style.** This hierarchy governs every code decision. Higher-priority concerns always win conflicts.

**4.7 — Known limitations are documented, not hidden.** Constraints the design cannot fully solve — prompt injection being the primary example — are documented explicitly. The NIST AI 100-2 taxonomy notes that theoretical impossibility results on adversarial ML mitigations exist. The facilitator approval flow is the ultimate defense.

**4.8 — Defense in depth, not silver bullets.** No single defense solves prompt injection, exfiltration, or cross-model poisoning. SACP uses six coordinated defense layers: network, application, data, AI/ML, operational, and governance. Every security decision must identify its layer and whether adjacent layers provide backup. (Framework: attack surface analysis §14)

**4.9 — Secure by design.** Defenses do not cease at role boundary. The security pipeline (§8) MUST validate every AI response on every persistence path; no role — including facilitator — silently bypasses defenses. The facilitator's role is to direct workflow, not to disable security. Resolution (spec 012 FR-006, 2026-05-01): approach (b) — re-pipeline + explicit-override-with-logged-justification. Approved and edited review-gate drafts re-enter the pipeline before persisting; if content re-flags the facilitator must supply an `override_reason` or reject the draft. Approved overrides are logged to `security_events` with `layer='facilitator_override'` and `override_actor_id`. 007 §FR-005 amended accordingly.

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
- Export sessions (markdown, JSON, external memory bulk import).
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

**6.8 — Container:** Docker Compose, FastAPI + PostgreSQL 16. Debian slim-bookworm base (`python:3.14.4-slim-bookworm`) — chosen over Alpine to keep glibc available so wheels (torch, numpy, sentence-transformers) install ABI-compatibly without forcing source builds. PostgreSQL co-located on the same Docker network. LiteLLM network-isolated. No Kubernetes, Helm, or cloud-managed services in Phase 1+2.

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

- **Cross-model safety profiling.** The orchestrator maintains per-model safety tiers. Outputs from low-safety and untrusted models pass through additional validation. Sessions can enforce minimum model tiers for participation. *(Phase 1+2 status: deferred — minimum-model-tier session policy ships, but per-model safety-tier registry + tier-conditional validation is Phase 3+. Trigger: any deployment with a documented adversarial-model-class concern OR addition of a model class with known safety regressions.)*

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
- **MCP SSE hardening.** Sessions bound to client IP (002 §FR-016). Connection limits enforced (per-session subscriber cap per 006 §FR-019). Tool description hashing — *Phase 1+2 status: deferred (tool descriptions are static at registration time; rug-pull threat surface is small until external MCP integration lands). Trigger: any external MCP server integration OR a documented incident where tool descriptions changed unexpectedly.* (Details: attack surface analysis §8)
- **DoS multiplication awareness.** Hard timeouts on all LiteLLM calls. CPU-bound operations offloaded from the async event loop. Per-participant budgets enforced at the orchestrator level. (Details: attack surface analysis §12)
- **Dependency security.** All dependencies pinned with hash verification. SBOM maintained. LiteLLM network-isolated. ML models loaded in SafeTensors only. CI runs `pip-audit` and `safety`. (LiteLLM supply chain history: attack surface analysis §10)
- **Banned functions.** No `eval()`, `exec()`, `pickle.loads()` on untrusted data, or `subprocess` with `shell=True`. (Full list: coding-standards.md)

---

## 10. Phase Boundaries

Each phase is a complete, usable system. No phase depends on a future phase to function.

**Phase 1 (MVP):** Two participants, one facilitator. Static token auth. LiteLLM bridge (network-isolated). 4-tier delta-only system prompts with canary tokens. Serialized turn loop with all 8 routing modes, complexity classifier (pattern-matching), interrupt queue, multi-signal convergence detection, adaptive cadence, adversarial rotation, per-turn timeouts. Context assembly with 5-priority token budget and summarization checkpoints. `[NEED:]` tool proxy with allowlist and SSRF protection. Full AI security pipeline (spotlighting, sanitization, safety profiling, multi-layer output validation, jailbreak detection, prompt extraction defense, role-based tool scoping, exfiltration defense, trust-tiered content model). Error detection with retry and circuit breaker. TLS, rate limiting, input validation, response size enforcement, origin validation, MCP SSE binding, CORS/CSP, log scrubbing. Append-only logs with restricted DB permissions. Admin audit log. Export (markdown, JSON, external memory). One-sided conversation detection. Docker Compose. SafeTensors-only. SBOM. No web UI. No artifact store.

**Phase 2 (shipped 2026-04-29; audit window closed 2026-05-04):** Web UI (port 8751) with WebSocket streaming, review-gate UI, three-path guest onboarding (sign-in / create / request-to-join, US11+US12), facilitator admin panel, decision/proposal workflow (US7), summary panel (US9), participant health indicators with circuit-breaker visibility (US10), secure markdown rendering with XSS defenses (US8), debug-export tool (spec 010). Followed by an extensive post-deploy hardening pass: 11-spec security audit sweep, perf-amendment landings (PR #163), Trivy CVE-2025-47273 fix iterations, Tier 1-3 quality checklists. **Deferred from Phase 2 to Phase 3:** session forking, multi-project support, participant-facing audit log subset, artifact store (blob KV), per-participant context optimization, envelope encryption migration, OAuth 2.1 with PKCE, MCP-to-MCP topology 7 integration. Pre-Phase-3 audit window: 419 items shipped, 55 explicitly accepted as Phase-3-trigger residuals, zero unchecked at closure.

**Phase 3 (declared started 2026-05-05):** 3–5 participants. Branching and rollback with UI. Sub-sessions with conclusion merging. External memory integration. Relevance-based routing, broadcast mode. Ollama/vLLM local model support. OAuth 2.1 with PKCE replaces static tokens. Step-up authorization. Artifact store enhancements. Git-backed decision tracking. Spec 013 (high-traffic-mode / broadcast) and spec 014 (dynamic mode assignment / signal-driven controller) drafted with full `/speckit.plan` artifacts; tasks + implementation begin per Constitution §14.1.

**Phase 4:** A2A federation. Agent Card discovery. Hierarchical sub-sessions. Data retention policies. Formal protocol spec. Evaluate Inter-Agent Trust Protocol for multi-sovereign trust.

**Voice-mediated participants (Phase 3+, deferred):** Voice participant evaluation deferred. If admitted, the architectural commitments in `local/comm-design/` govern: STT canonicalization on every hop, TTS re-synthesis from canonical text, refusal of in-band protocol negotiation, voice participant trust tier, no raw-audio federation, voice participant disclosure.

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

**V14 — Performance budgets specified and instrumented.** Every feature spec with a hot path MUST codify per-stage latency budgets (P50, P95, P99 where measurable), memory ceilings, and degradation-under-load behavior — not as observational targets but as enforceable contracts. Per-stage timings MUST be captured into structured logs (cross-ref 003 §FR-030 stage timings into `routing_log`, 007 §FR-020 layer durations into `security_events`) so regressions are diagnosable per-stage rather than aggregate-only. PR #163 codified the contracts; instrumentation implementation work is outstanding but the validation rule is binding for all future specs.

**V15 — Security pipeline fail-closed.** Pipeline-internal failures (regex compile errors, unicode normalization errors, layer crashes) MUST fail closed: skip the turn with a documented `reason='security_pipeline_error'`, write a `security_events` row with `layer='pipeline_error'`, and DO NOT increment the participant's circuit-breaker counter (the failure is the system's, not the participant's). Cross-ref 007 §FR-013 + 003 §FR-023. Combined with §4.9 (secure by design), this rule means defenses-by-default extend to defense-when-defense-itself-fails.

**V16 — Configuration validated at startup.** Every `SACP_*` env var MUST have a documented type, valid range, and fail-closed semantics for invalid values. The application MUST validate every var at startup BEFORE binding any port or accepting any connection; an invalid value MUST cause the process to exit with a clear error rather than silently accepting an out-of-range default. Catalog of all env vars + per-var validation rules is the deliverable of the AUDIT_PLAN batch 5 config-validation audit.

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
| `docs/red-team-runbook.md` | Red-team operational guide | Adversarial-test workflow, known-incident catalog (Round02 Cyrillic homoglyph injection, etc.), pattern-list update process per 007 §FR-017 |
| `docs/env-vars.md` | Environment variable catalog | Per-var defaults, types, ranges, blast radius, validation rules per V16; companion to `src/config/validators.py` |
| `docs/pattern-list-update-workflow.md` | Pattern-list update workflow | Four-step workflow (capture → PR within one cycle → corpus + regression test + pattern + runbook update → land within one cycle) for promoting red-team incidents to detection patterns per 007 §FR-017 |
| `docs/threat-model-review-process.md` | Threat-model freshness review | Per-Phase-boundary cadence + four trigger conditions (new red-team category, new participant capability, dependency major version, provider regression) + ownership |
| `docs/adr/` | Architectural decision records | MADR 4.0 lightweight format, one file per decision (NNNN-short-title.md). Decisions outside §14.5 Constitution scope (single-file refactor patterns, fire-and-forget summarization rationale, etc.) |
| `docs/api-versioning.md` | API versioning and deprecation policy | Current state (no versioning Phase 1/2), MCP protocol divergence, Phase 3 strategy, breaking-change definition, operator compatibility window, feature-flag registry, rollback approach |

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

### 14.7 — Audit work

Audits are systematic reviews of existing specs/code against a quality dimension (security, performance, compliance, testability, operations, reliability, accessibility, ux, etc.). They produce findings; findings produce work that flows through the existing categories (spec amendments per §14.2, new features per §14.1, hotfixes per §14.3 if a security finding requires immediate response).

Conventions:

1. **One-off formal audit** (single spec × type) → run `/speckit.checklist <type>` on a `docs/<slug>` branch. Produces a committed `specs/NNN/checklists/<type>.md` file as a permanent artifact. Used for the original 2026-04-29 security sweep + tier-1-3 quality checklists (PRs #157-#163).

2. **Sweep-style audit window** (many specs × many types as a coordinated effort) → track in a gitignored local action plan (`AUDIT_PLAN.local.md`). Action items, not formal checklists. Findings get promoted to spec amendments via §14.2 PRs as they're resolved. The pre-Phase-3 audit window (opened 2026-04-29) uses this pattern; ~37 audit topics tracked.

3. **Branch naming**: `audit/<topic>` for sweep audit work that isn't yet a spec amendment; `fix/<slug>` for the resulting amendment PRs.

4. **Cross-cutting findings** (the same gap appears across many audits — env-var inventory, FR-to-test traceability, benchmark fixture, pattern-list update workflow) are consolidated into single-PR resolutions rather than per-audit piecemeal work.

5. **Audit work does NOT consume a numbered feature slot.** It runs against existing specs.

The pre-Phase-3 audit window is gating: Phase 3 development should not start until the audit work is sufficiently closed (per facilitator judgment — there is no fixed-percentage gate, but high-value security and reliability findings should be resolved or explicitly accepted).

### 14.8 — Spec versioning convention

When a spec is amended substantively (per §14.2), the spec gains a header
block near the top recording its current version:

```markdown
**Spec Version**: M.N.P | **Last Amended**: YYYY-MM-DD | **Amended In**: PR #NNN (one-line summary)
```

Versioning rules (semantic-versioning analog):

- **PATCH** (1.0.0 → 1.0.1): typo fix, clarification that doesn't tighten or relax any FR
- **MINOR** (1.0.x → 1.1.0): new FR added, new acceptance scenario, FR semantics tightened or relaxed without breaking existing tests
- **MAJOR** (1.x → 2.0): existing FR removed or replaced with incompatible semantics; existing tests retired

Applied retroactively only when a spec is next amended (no bulk retroactive
versioning sweep). Specs without a version header are treated as `1.0.0`
implicitly until their first amendment under this convention.

The version header is informational; CI does not yet enforce monotonic
version increase. A future enhancement may add a `scripts/check_spec_versions.py`
gate; the bar is empirical evidence of two specs accidentally landing the
same version, not premature codification.
