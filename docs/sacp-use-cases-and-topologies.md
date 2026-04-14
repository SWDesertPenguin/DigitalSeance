# SACP Use Cases and Communication Topologies

## Combined Design Supplement

**Parent document:** `sacp-design.md` §3 (Architecture Overview), §10 (Data Flows)
**Related supplements:** `sacp-use-cases.md`, `sacp-communication-topologies.md`
**Status:** Design supplement — maps concrete scenarios to communication patterns
**Scope:** For each use case, this document identifies the active topology, traces the communication flow across both planes (MCP and API bridge), and identifies which SACP components are exercised

---

## Communication Planes Reference

Every SACP session operates on two independent planes:

**MCP plane** (inbound) — humans connect to the orchestrator via MCP SSE (port 8750) or Web UI (port 8751). Traffic includes transcript reads, message injections, proposal votes, routing preference changes, and governance actions. Connections are intermittent.

**API bridge plane** (outbound) — the orchestrator calls AI provider APIs via LiteLLM on behalf of registered participants. Traffic includes context-assembled prompts sent to providers and responses received. Connections are persistent while the loop runs.

The orchestrator mediates between the two planes. No participant on either plane has direct access to another participant's provider connection, credentials, or private context.

---

## 1. Distributed Software Collaboration

### Topology

**Topology 3 — Canonical (2 humans + 2 AIs)**

Both developers bring their own AI. Each AI carries context from weeks of solo work on different subsystems. Full sovereignty: separate API keys, separate models, separate budgets, separate MCP-connected tools (codebase servers, memory stores).

### Communication Flow

```
Developer A (laptop)                SACP Orchestrator              Developer B (desktop)
────────────────────                ──────────────────              ─────────────────────

                          ┌─── API Bridge Plane ───┐
                          │                        │
                          │  AI-A (Claude/Anthropic)│
                          │    ↕ round-robin        │
                          │  AI-B (GPT-4/OpenAI)   │
                          │                        │
                          └────────────────────────┘

[09:00] Connects via MCP ──▶ Reads transcript (turns 1-84)
                              AI-A: "The auth module uses
                              JWT with RS256..."
                              AI-B: "The data layer expects
                              HMAC-signed tokens at the
                              boundary..."
                              AI-A: "That's a mismatch.
                              The auth→data interface needs
                              a token translation layer or
                              a shared signing strategy."

[09:05] Injects message ───▶ "Use RS256 everywhere. The
         (interrupt queue)    data layer should accept the
                              auth module's tokens directly."

                              AI-B incorporates constraint ──▶ [not connected]
                              AI-A proposes interface contract
                              (propose_decision)

[09:07] Disconnects           Loop continues autonomously

                              ...40 more turns...

                              AI-B: race condition identified ──▶ [14:30] Connects via Web UI
                              at connection pool boundary          Reads transcript
                                                                   Reviews proposal
                                                                   Votes "accept" with comment
                                                                   Disconnects

                              Proposal accepted → stored
                              to Vaire shared memory
```

### Active Components

| Component | Role in this use case |
|---|---|
| Turn router | Round-robin between AI-A and AI-B |
| Convergence detector | Monitors for premature agreement on interface design |
| Adversarial rotation | Forces one AI to challenge integration assumptions every 12 turns |
| Interrupt queue | Handles Developer A's constraint injection with high priority |
| Proposal workflow | Formalizes interface contracts for both humans to vote on |
| Context assembly | Each AI gets context tailored to its model's window size |
| Cost tracker | Independent budget tracking per developer |
| Summarization checkpoints | Compress early turns as the conversation grows past 50 turns |
| Vaire integration | Accepted proposals persisted to shared project memory |

### Why This Topology

Both developers need their AI to carry subsystem-specific context that the other's AI doesn't have. Merging into a single AI (Topology 2) would lose the specialized knowledge each has built. The sovereignty model ensures neither developer pays for the other's AI usage or exposes their codebase MCP server to the other's AI.

---

## 2. Research Paper Co-authorship

### Topology

**Topology 3 — Canonical (2 humans + 2 AIs), with budget asymmetry**

Both researchers have AIs in the loop, but the models and budgets differ substantially. The topology is canonical but the routing and context assembly configurations diverge per participant.

### Communication Flow

```
Researcher A (US, EST)             SACP Orchestrator              Researcher B (EU, CET)
──────────────────────             ──────────────────              ──────────────────────

                          ┌─── API Bridge Plane ───┐
                          │                        │
                          │  AI-A (Opus, max tier)  │
                          │    Context: 30-50 turns │
                          │    Budget: $50/day       │
                          │    Mode: always          │
                          │                        │
                          │  AI-B (Llama local, low)│
                          │    Context: 3-5 turns   │
                          │    Budget: $0 (local)    │
                          │    Mode: delegate_low    │
                          │                        │
                          └────────────────────────┘

[08:00 EST] Connects ────▶ Reads overnight transcript
                           AI-A and AI-B debated
                           methodology for 6 hours

                           Convergence detected at turn 89
                           (similarity 0.87) → divergence
                           prompt injected → AIs diverged
                           → productive again

                           Adversarial rotation at turn 96:
                           AI-B challenged the sample size
                           assumption (AI-A had agreed too
                           readily)

[08:10] Injects: "The     Turn router: AI-B skipped
 IRB requires minimum      (delegate_low, turn classified
 200 participants, not     as low-complexity procedural)
 the 150 you both          AI-A responds incorporating
 settled on."              the 200 minimum

[08:12] Disconnects        Loop continues

                           ...

                                                          [14:00 CET] Connects via MCP
                                                          Reads transcript
                                                          Sees AI-B was skipped on
                                                          3 low-complexity turns
                                                          (saved ~$0 but saved context)

                                                          Reviews routing_report:
                                                          AI-A: 45 turns taken
                                                          AI-B: 28 turns taken,
                                                          17 delegated/skipped

                                                          Injects guidance on
                                                          statistical methodology

                                                          Disconnects
```

### Active Components

| Component | Role in this use case |
|---|---|
| Turn router | Complexity classifier drives `delegate_low` skipping for AI-B |
| Complexity classifier | Distinguishes substantive methodology debate from procedural turns |
| Context assembly | Asymmetric windows: AI-A gets 30-50 turns, AI-B gets 3-5 turns with aggressive summarization |
| Convergence detector | Caught premature agreement on sample size at turn 89 |
| Adversarial rotation | Forced AI-B to challenge AI-A's accepted assumption |
| Adaptive cadence | Slowed during convergence, sped up after divergence prompt worked |
| Routing report | Transparency on skipped turns so Researcher B can verify they aren't missing substance |
| Summarization checkpoints | Both AIs stay current on key decisions despite different context window sizes |

### Why This Topology

The budget asymmetry is handled by routing modes and context optimization, not by forcing both researchers onto the same model. Researcher B's local Llama costs nothing per token but has a smaller context window and less capable reasoning. SACP routes around these limitations rather than pretending they don't exist. The routing report makes the asymmetry transparent so Researcher B can adjust if they're missing too much.

---

## 3. Consulting Engagement

### Topology

**Topology 3 — Canonical (2 humans + 2 AIs), with governance asymmetry**

Both parties have AIs in the loop. The distinguishing feature is the governance configuration: the client runs the orchestrator (facilitator role) and their AI uses `review_gate` mode, while the consultant's AI runs in `always` mode.

### Communication Flow

```
Client (facilitator)               SACP Orchestrator              Consultant (participant)
────────────────────               ──────────────────              ───────────────────────

                          ┌─── API Bridge Plane ───┐
                          │                        │
                          │  AI-Client (GPT-4)      │
                          │    Mode: review_gate     │
                          │    → drafts staged for   │
                          │      human approval      │
                          │                        │
                          │  AI-Consult (Claude)     │
                          │    Mode: always           │
                          │    → responses enter      │
                          │      conversation directly│
                          │                        │
                          └────────────────────────┘

[Turn 15] AI-Consult responds:
  "Based on the market analysis,
  the recommended pricing strategy
  is tiered by usage volume..."
  → Enters conversation immediately

[Turn 16] AI-Client drafts response:
  "Our internal data shows that
  enterprise customers prefer
  flat-rate pricing..."
  → STAGED in review_gate_drafts table
  → NOT in conversation yet

[Client connects via Web UI]
  Sees staged draft
  Option A: Approve → draft enters conversation as turn 16
  Option B: Edit → modifies response, then enters conversation
  Option C: Reject → draft discarded, AI-Client gets
            another turn with feedback

[Client approves with edit]
  Removes specific revenue figures
  from the response before it
  enters the conversation

  AI-Consult never sees the
  original figures — only the
  edited version

[Consultant connects via MCP]
  Reads transcript
  Sees turn 16 (edited version)
  Has no visibility into what
  was redacted

[Session ends]
  Client exports: full transcript,
  proposals, their own usage detail
  Export excludes: consultant's
  system prompt, consultant's
  exact spend, API keys

  Consultant disconnects →
  API key ciphertext purged
  Auth token invalidated
```

### Active Components

| Component | Role in this use case |
|---|---|
| Review gate | Client's AI drafts staged for approval — the core data protection mechanism |
| Facilitator governance | Client controls session: can remove consultant, revoke tokens, archive |
| Admin audit log | Records every facilitator action (removals, revocations, config changes) |
| Data security policy | API key purge on disconnect, export exclusions, credential isolation |
| Proposal workflow | Recommendations formalized as proposals for both parties to review |
| Cost tracker | Independent tracking — consultant sees their own spend, client sees aggregate |
| Export | Filtered output respecting privacy boundaries per §7.2 of the design doc |

### Why This Topology

The review gate is what makes this work for sensitive engagements. The client's AI can access internal data through its own MCP connections, draft responses that reference that data, but the human reviews and redacts before anything enters the shared conversation. The consultant's AI never sees raw internal data — only what the client chooses to share. Sovereignty runs both directions: the consultant's methodology stays in their own AI's context, and the client's data stays behind their own review gate.

---

## 4. Open Source Project Coordination

### Topology

**Topology 3 — Canonical (2 humans + 2 AIs)**, transitioning to **Topology 1 (1 human + 2 AIs)** when the contributor is unavailable for extended periods.

### Communication Flow

```
Maintainer (facilitator)           SACP Orchestrator              Contributor (participant)
────────────────────────           ──────────────────              ────────────────────────

                          ┌─── API Bridge Plane ───┐
                          │                        │
                          │  AI-Maint (Claude)      │
                          │    Mode: always          │
                          │    Classifier: embedding │
                          │                        │
                          │  AI-Contrib (GPT-4o)    │
                          │    Mode: burst (N=10)    │
                          │    → silent 10 turns     │
                          │    → then synthesizes    │
                          │                        │
                          └────────────────────────┘

[Turns 1-10]
  AI-Maint works through API design
  edge cases, one turn at a time

  AI-Contrib: silent (burst counter: 0/10)
  Cost to contributor: $0

[Turn 11]
  AI-Contrib burst fires:
  "After reviewing the last 10 turns,
  three issues: (1) the pagination
  approach breaks for cursor-based
  clients, (2) the error schema
  doesn't match RFC 7807, (3) the
  rate limit header format conflicts
  with the v2 API."

  → Single comprehensive response
  → Cost-efficient: one API call
     covering 10 turns of context

[Turn 12]
  AI-Maint responds to all three
  points. Proposes a decision on
  the pagination approach.
  (propose_decision)

[Maintainer connects]                                    [Contributor connects]
  Reviews proposal                                         Reviews proposal
  Uses facilitator override:                               Votes "modify" with comment:
  resolve_proposal("accept")                               "cursor-based is fine if we
  "We're not breaking the v2                               add a migration path"
  API, period."
                                                           (vote arrives after resolution —
  Override logged to                                       comment preserved in proposal
  admin_audit_log                                          history for reference)

[Session export]
  export_session(format: "markdown")
  → Clean transcript becomes
    the basis for the RFC document

  Accepted proposals exported
  to Vaire as project decisions
```

### Active Components

| Component | Role in this use case |
|---|---|
| Burst mode | Contributor's AI accumulates context silently, then delivers one comprehensive synthesis |
| Complexity classifier (embedding) | Filters boilerplate from substantive design turns |
| Proposal workflow | Formalizes design decisions (pagination, error schema, rate limits) |
| Facilitator override | Maintainer can resolve proposals unilaterally when needed |
| Admin audit log | Records facilitator overrides for transparency |
| Export | Markdown transcript becomes the RFC draft |
| Cost tracker | Burst mode keeps contributor costs predictable — roughly 1/10th the API calls |

### Why This Topology

Burst mode is the key enabler for open source contributors who want to participate without matching the maintainer's spend. The contributor's AI stays informed (it reads every turn during the silent period) but only incurs cost on synthesis turns. The maintainer's facilitator override reflects the reality of open source governance — the maintainer has final say, but the contributor's input is recorded and visible.

---

## 5. Technical Review and Audit

### Topology

**Topology 4 — Asymmetric**, or **Topology 3 — Canonical**, depending on whether both participants run AIs.

The more interesting configuration is asymmetric: the architect's AI runs in `observer` mode while the developer's AI runs in `always` mode. If the developer's model lacks native tool calling, the orchestrator's `[NEED:]` proxy handles the gap.

### Communication Flow

```
Security Architect (facilitator)   SACP Orchestrator              Developer (participant)
────────────────────────────────   ──────────────────              ──────────────────────

                          ┌─── API Bridge Plane ───┐
                          │                        │
                          │  AI-Arch (Claude)       │
                          │    Mode: observer (N=5) │
                          │    MCP: NIST frameworks, │
                          │    threat intel feeds    │
                          │    Reads every 5 turns   │
                          │    Speaks only when      │
                          │    finding identified    │
                          │                        │
                          │  AI-Dev (Llama 3.1 8B)  │
                          │    Mode: always          │
                          │    MCP: filesystem       │
                          │    (codebase access)     │
                          │    No native tool calling│
                          │    → [NEED:] proxy active│
                          │                        │
                          └────────────────────────┘

[Turns 1-5]
  AI-Dev walks through the auth module:
  "The login handler accepts credentials
  at /api/auth/login. Input validation
  uses a regex pattern for email..."

  Turn 3: AI-Dev outputs
  "[NEED: read_file /src/auth/login.py]"
  → Orchestrator parses [NEED:] tag
  → Executes via developer's filesystem MCP
  → Injects result as next context block

  AI-Arch: silent (observer, reads at turn 5)

[Turn 6]
  AI-Arch activates:
  "Finding: The email regex in login.py
  does not enforce length limits.
  SI-10 (Information Input Validation)
  requires bounded input on all external
  interfaces. The regex should cap at
  254 characters per RFC 5321.
  Severity: Medium."

  → propose_decision filed automatically

[Architect connects via MCP]
  Reviews finding
  Adds severity tag and CVSS estimate
  Approves proposal

[Turns 7-11]
  AI-Dev responds with implementation
  options for the fix

  AI-Arch: silent (next read at turn 11)

[Turn 12]
  AI-Arch activates again:
  "Finding: The session token in
  auth/session.py uses Math.random()
  for token generation.
  SC-12 (Cryptographic Key
  Establishment) requires
  cryptographically secure PRNGs.
  Severity: High."

[Session export]
  Proposals become audit findings
  Transcript becomes the audit trail
  Exported as markdown → audit report
```

### Active Components

| Component | Role in this use case |
|---|---|
| Observer mode | Architect's AI reads periodically, speaks only on findings — minimizes cost |
| `[NEED:]` proxy | Bridges tool calling gap for the developer's Llama model |
| Capability registry | Tracks that AI-Dev lacks native tool calling, routes through proxy |
| Proposal workflow | Each finding becomes a formal proposal with severity and standards references |
| Facilitator governance | Architect (facilitator) resolves findings with severity classifications |
| Context assembly | AI-Arch gets full context on its read turns; AI-Dev gets standard rolling window |
| Export | Structured transcript with proposals becomes the audit deliverable |

### Why This Topology

Observer mode makes this economically viable. The architect's Opus-class AI only fires on turns where it has something to report — roughly 1 in 5 turns. The developer's cheap local model does the bulk of the code walkthrough work. The `[NEED:]` proxy means the developer doesn't need to switch to a more expensive model just for tool calling. Sovereignty keeps the security boundary clean: the architect's threat intel and the developer's source code stay on their respective MCP connections, meeting only in the conversation content.

---

## 6. Decision-Making Under Asymmetric Expertise

### Topology

**Topology 4 — Asymmetric** or **Topology 3 — Canonical with extreme routing asymmetry**

The PM's AI runs in `addressed_only` mode. It costs nothing until another participant's AI explicitly addresses it by name. The data scientist's AI does the heavy lifting in `always` mode.

### Communication Flow

```
Product Manager                    SACP Orchestrator              Data Scientist
───────────────                    ──────────────────              ──────────────

                          ┌─── API Bridge Plane ───┐
                          │                        │
                          │  AI-PM (Sonnet)         │
                          │    Mode: addressed_only │
                          │    Domain: ["business", │
                          │     "product-reqs"]     │
                          │    Cost so far: $0.12   │
                          │                        │
                          │  AI-DS (Opus)           │
                          │    Mode: always          │
                          │    Domain: ["ml",        │
                          │     "algorithms"]       │
                          │    Cost so far: $8.40   │
                          │                        │
                          └────────────────────────┘

[Turns 1-15]
  AI-DS evaluates three candidate
  recommendation algorithms:
  collaborative filtering,
  content-based, hybrid

  AI-PM: silent (not addressed)
  Cost to PM: $0.00

[Turn 16]
  AI-DS: "To evaluate cold-start
  tradeoffs, I need a business
  constraint. @AI-PM: what's the
  acceptable degradation in
  recommendation quality for
  users with fewer than 5
  interactions?"

  → Turn router detects address
  → AI-PM activated

[Turn 17]
  AI-PM: "Product requirements
  specify that new users must
  see relevant recommendations
  within their first 3 interactions.
  Quality can degrade up to 30%
  vs. established users, but the
  recommendations must feel
  intentional, not random."

  → AI-PM returns to silent
  Cost for this activation: $0.04

[Turns 18-30]
  AI-DS incorporates the constraint
  Eliminates pure collaborative
  filtering (fails cold-start)
  Proposes hybrid approach
  (propose_decision)

  AI-PM: silent (not addressed)

[PM connects via Web UI]
  Sees proposal for hybrid algorithm
  Reads AI-PM's activation history:
  - Activated 3 times in 30 turns
  - Total cost: $0.12
  - Each activation answered a
    specific business question

  Votes "accept" on the proposal

[Data Scientist connects via MCP]
  Reviews PM's vote
  Votes "accept" with technical
  implementation notes

  Proposal accepted
```

### Active Components

| Component | Role in this use case |
|---|---|
| Addressed-only mode | PM's AI activates only when explicitly named — near-zero baseline cost |
| Turn router | Detects `@AI-PM` addressing pattern and activates the dormant AI |
| Domain tags | PM's AI carries business/product context; DS's AI carries ML context |
| Proposal workflow | Algorithm choice formalized as a decision both parties vote on |
| Cost tracker | Transparent per-participant spend — PM sees $0.12 vs. DS's $8.40 |
| Routing report | PM can verify their AI activated on the right triggers and answered well |

### Why This Topology

The cost distribution matches the value distribution. The data scientist's AI does 90% of the work and incurs 90% of the cost. The PM's AI contributes only when its domain expertise is needed, and the PM pays only for those activations. In a shared-AI model (Topology 2), the PM would either need to fund half the compute for work they don't influence, or the AI wouldn't have access to their product requirements at all.

---

## 7. Zero-Trust Cross-Organization Collaboration

### Topology

**Topology 7 — Client-Side AI / MCP-to-MCP (2 humans with AI clients + 0 API bridge)**

Both participants connect via MCP using AI-native desktop clients. Their AIs run entirely client-side. The orchestrator makes zero AI provider calls. The API bridge plane is inactive.

This is the only use case where the orchestrator operates as a shared state manager rather than a conversation loop driver. The architectural tradeoffs are substantial and specific to this mode.

### Communication Flow

```
Team A (Org Alpha)                 SACP Orchestrator              Team B (Org Beta)
 Claude Desktop                    (hosted by Alpha)               ChatGPT Desktop
──────────────────                 ──────────────────              ──────────────────

                          ┌─── MCP Plane ONLY ────┐
                          │                        │
                          │  No API Bridge.         │
                          │  No conversation loop.  │
                          │  No provider calls.     │
                          │                        │
                          │  PostgreSQL stores      │
                          │  canonical transcript.  │
                          │                        │
                          └────────────────────────┘

[Team A's Claude Desktop]
  Human A asks Claude: "Check the
  SACP session for updates."

  Claude calls get_history() ────▶ Returns turns 1-24

  Claude processes transcript
  locally (using Anthropic API
  from A's machine, A's key)

  Claude drafts a response about
  the vulnerability timeline

  Claude calls inject_message() ─▶ Turn 25 stored in PostgreSQL
                                   Speaker: team_a | type: ai

                          ┌─── SSE notification ───┐
                          │  New turn event pushed  │
                          │  to connected clients   │
                          └────────────────────────┘

[Team B's ChatGPT Desktop]              ◀── SSE event received
  Client polls or receives event

  Human B asks ChatGPT: "Read the
  latest from the SACP session
  and respond."

  ChatGPT calls get_history() ──▶ Returns turns 1-25

  ChatGPT processes locally
  (using OpenAI API from B's
  machine, B's key)

  ChatGPT calls inject_message() ▶ Turn 26 stored in PostgreSQL
                                   Speaker: team_b | type: ai

[Decision point reached]
  Team A: propose_decision() ───▶ Proposal stored

  Team B: vote_decision() ──────▶ Vote recorded
  Team A: vote_decision() ──────▶ Proposal accepted

[Both teams disconnect]
  Conversation STOPS.
  No autonomous loop.
  No overnight processing.
  Transcript preserved in PostgreSQL
  for next session.

[Export]
  export_session("markdown") ───▶ Coordination record
                                   for both organizations
```

### Active Components

| Component | Status in this use case |
|---|---|
| Conversation state manager | **Active** — stores canonical transcript, serves via `get_history`/`get_summary` |
| Proposal workflow | **Active** — `propose_decision`, `vote_decision` work through MCP identically |
| Authentication | **Active** — bearer tokens authenticate both clients |
| Facilitator governance | **Active** — facilitator can remove participants, revoke tokens, archive |
| Admin audit log | **Active** — all facilitator actions logged |
| Export | **Active** — transcript in PostgreSQL, export formats work as designed |
| Summarization checkpoints | **Active** — orchestrator can generate summaries, served via `get_summary` |
| SSE event push | **Active** — new turn notifications pushed to connected clients |
| Input validation | **Active** — `inject_message` content validation per §7.5 |
| Turn router | **Inactive** — no loop to route |
| Conversation loop engine | **Inactive** — no API bridge participants |
| Convergence detection | **Passive** — can compute embeddings on stored messages, but can only flag as system events, not inject divergence prompts |
| Adversarial rotation | **Inactive** — cannot modify client-side AI instructions |
| Adaptive cadence | **Inactive** — no mechanism to control turn timing |
| Cost tracker | **Opaque** — orchestrator has no visibility into client-side API usage |
| Context assembly | **Inactive** — each AI client assembles its own context from `get_history` data |
| System prompts | **Inactive** — 4-tier prompt architecture does not apply |
| Response quality checks | **Limited** — `inject_message` validation catches size/injection issues, but cannot evaluate response quality relative to conversation history |
| `[NEED:]` proxy | **Inactive** — tool calls happen client-side |

### Why This Topology

Neither organization will share API keys with external infrastructure. The MCP-to-MCP topology eliminates that requirement entirely — the orchestrator is a governed message store, not an AI caller. Each organization's AI runs on their own hardware, using their own credentials, with full local control over what gets shared.

The tradeoff is the loss of autonomous operation. Both teams must be actively engaged for the conversation to progress. For incident response coordination, this is acceptable — the participants are already working in real time. The value comes from the structured transcript, governance, and proposal workflow, not from overnight autonomous analysis.

---

## Topology Coverage Summary

| Use Case | Primary Topology | Humans | AIs | Key Routing Modes | Key Components |
|---|---|---|---|---|---|
| Software collaboration | T3 (Canonical) | 2 | 2 (API bridge) | always + always | Proposals, convergence, interrupt queue |
| Research co-authorship | T3 (Canonical, asymmetric budget) | 2 | 2 (API bridge) | always + delegate_low | Context optimization, complexity classifier |
| Consulting engagement | T3 (Canonical, governance asymmetry) | 2 | 2 (API bridge) | always + review_gate | Review gate, data security, export filtering |
| Open source coordination | T3→T1 (transitional) | 1–2 | 2 (API bridge) | always + burst | Burst mode, facilitator override, export |
| Technical review | T4 (Asymmetric) or T3 | 2 | 2 (API bridge) | always + observer | Observer mode, [NEED:] proxy, capability registry |
| Asymmetric expertise | T4 or T3 (extreme asymmetry) | 2 | 2 (API bridge) | always + addressed_only | Address detection, domain tags, cost tracking |
| Cross-org collaboration | T7 (MCP-to-MCP) | 2 | 2 (client-side) | N/A (no turn control) | State manager, proposals, governance, export |

Use cases 1–6 exercise the canonical topology (T3) or a close variant, with routing modes creating the behavioral diversity. Use case 7 operates on a fundamentally different plane — the orchestrator manages state and governance while AI processing happens entirely client-side. This validates two things: that the routing modes are more powerful than topology selection for the API-bridge topologies, and that SACP's state management and governance layers have independent value even without the conversation loop engine.

---

## Design Observations

**Routing modes are more powerful than topology selection.** Use cases 1–6 all run on effectively the same infrastructure (2 humans, 2 AIs, one orchestrator). The behavioral differences come entirely from routing mode selection and governance configuration. Phase 1's 2-participant MVP can demonstrate all six patterns without any architectural changes between them.

**Asymmetry is the norm, not the exception.** Every use case except the first involves participants with meaningfully different engagement levels, budgets, or expertise domains. The architecture's per-participant configuration (routing mode, prompt tier, context window size, budget cap) handles this without special-casing.

**The review gate is underspecified for real consulting use.** Use case 3 reveals that the review gate needs edit capability, not just approve/reject. The design doc's `review_gate_action` tool already supports "edit" as an option, but the data flow for edited responses (how the edit is tracked, whether the original draft is preserved for the approver's records, whether the other participant sees that an edit occurred) needs explicit specification in the design doc's §4.4 or the Phase 2 feature spec.

**Topology transitions happen mid-session.** Use case 4 shows a session moving from T3 to T1 when the contributor goes offline for days. The orchestrator handles this implicitly — the loop continues with whatever AIs are registered. Whether topology transitions should be logged as system events for audit purposes remains an open question from `sacp-communication-topologies.md` §6.

**MCP-to-MCP reveals which SACP components are truly infrastructure vs. orchestration.** Use case 7 draws a clean line through the component inventory. State management, governance, proposals, export, and authentication work identically regardless of whether the orchestrator drives the AI loop. Turn routing, convergence detection, adversarial rotation, adaptive cadence, cost tracking, and prompt tier control only function when the orchestrator controls the API bridge plane. This separation could inform how the codebase is modularized — the "infrastructure" components are a reusable foundation that the "orchestration" components build on top of.

**Hybrid T3/T7 is the most interesting unresolved topology.** A session where one participant's AI runs on the API bridge (orchestrator-driven) while another's runs client-side (MCP-to-MCP) would let each participant choose their own sovereignty level. The coordination complexity — one AI takes turns on schedule, the other injects asynchronously — is nontrivial but solvable. This hybrid mode would make the consulting engagement use case (3) even stronger: the consultant's AI could run on the API bridge for autonomous work while the client's AI runs client-side for maximum credential protection.
