# SACP Communication Topologies

## Architectural Design Supplement

**Parent document:** `sacp-design.md` §3 (Architecture Overview), §10 (Data Flows)
**Status:** Design supplement — extends the core architecture with topology analysis
**Scope:** Enumerates all valid participant configurations, their communication patterns, architectural implications, and phase alignment

---

## 1. The Two Communication Planes

Every SACP session has traffic on two independent planes with fundamentally different characteristics.

**MCP plane** (inbound — port 8750 SSE / port 8751 Web UI). Humans connect to the orchestrator to read transcripts, inject messages, vote on proposals, and manage governance. Connections are intermittent by design. The protocol assumes drop-in/drop-out participation. Authentication is per-participant bearer token (Phase 1) or OAuth 2.1 with PKCE (Phase 3). All traffic is TLS-encrypted per §7.4.

**API bridge plane** (outbound — via LiteLLM). The orchestrator calls AI provider APIs on behalf of registered participants. These connections are persistent while the conversation loop runs, with each AI receiving its own system prompt tier, context assembly window, and provider-specific format translation. The orchestrator manages retry logic, circuit breakers, and budget enforcement on this plane.

A "participant" in the schema is a record in the `participants` table. The architecture does not enforce a 1:1 coupling between humans and AIs. A human can connect without an AI in the loop. An AI can run without its human being present. The topologies below are defined by how many of each type are active and how they relate to each other.

```
                MCP Plane (inbound)              API Bridge Plane (outbound)
                ──────────────────              ───────────────────────────

Human A ──MCP──┐                          ┌──LiteLLM──▶ Anthropic API (A's key)
               │                          │
Human B ──MCP──┼──▶ SACP Orchestrator ────┤
               │         │                │
Human C ──Web──┘         │                └──LiteLLM──▶ OpenAI API (B's key)
                         │
                    PostgreSQL 16
                  (canonical state)
```

Each participant's traffic stays on separate provider connections. The orchestrator mediates — it never proxies raw API credentials between participants or exposes one participant's provider connection to another.

---

## 2. Topology Definitions

Six distinct topologies are possible given the two-plane architecture. Three are design targets, one is an emergent behavior worth supporting, and two are degenerate cases outside SACP's value proposition.

---

### Topology 1 — Solo Operator, Multiple AIs

**Configuration:** 1 human (MCP) + 2+ AIs (API bridge)

The facilitator runs the orchestrator, connects via MCP or Web UI, and registers two or more AI participants — each with a different provider, model, API key, and budget. The AIs enter the autonomous conversation loop. The human drops in to read, steer, inject constraints, and resolve proposals.

**Use case:** A solo researcher sets up a structured debate between Claude Opus and GPT-4 on a design problem. Or runs a local Llama model against a cloud model to stress-test an argument from different reasoning perspectives. The human reads the transcript over coffee, injects a constraint ("the latency budget is 200ms, not 500ms"), and leaves. The AIs incorporate the constraint and continue.

**How it differs from single-operator agent frameworks:** Three properties distinguish this from CrewAI or AutoGen running the same models. First, the conversation persists across sessions — the human closes their laptop and the AIs keep going, picking up where they left off hours or days later. Second, each AI runs on a separate API key with independent budget tracking, even though one person owns both keys. Third, the human participates as a peer in the conversation (injecting messages, voting on proposals) rather than as an operator who configured a task pipeline and waits for output.

**Architectural behavior:** The turn router runs round-robin across the registered AIs. Convergence detection, adversarial rotation, and adaptive cadence operate normally. All routing modes are available per AI. The human's messages enter via the interrupt queue with high-priority tagging. Budget enforcement tracks each AI's key independently — the facilitator can set different spend caps per participant even though they own both.

**Phase alignment:** Phase 1 supports this directly. The 2-participant MVP with the facilitator as sole human is exactly this topology.

---

### Topology 2 — Multiple Humans, One Shared AI

**Configuration:** 2+ humans (MCP) + 1 AI (API bridge, shared)

Multiple humans connect via MCP or Web UI. A single AI is registered in the loop, not representing any specific human but serving as a shared assistant.

**Assessment: Degenerate case.** The sovereignty model breaks down when one AI serves multiple humans. The questions that define SACP's design — whose API key? whose system prompt? whose context? whose budget? — have no clean answers. The AI would need to be registered as a facilitator-owned participant, funded by the facilitator, with a generic system prompt. All humans would interact through MCP injection rather than being "represented."

The result is a multi-human chat with one AI assistant. The autonomous loop has nothing meaningful to do — there's no AI-to-AI conversation, no model heterogeneity producing different perspectives, no sovereignty to preserve. The complexity classifier has nothing to route. Convergence detection monitors similarity between one AI's responses and itself. Adversarial rotation has one participant to rotate across. The routing modes are irrelevant.

**What already serves this topology better:** Microsoft Copilot Cowork, Claude Teams, Slack AI, or any shared-AI workspace tool. These are purpose-built for multiple humans collaborating through a single AI. SACP's orchestration overhead adds cost and complexity without corresponding value.

**Phase alignment:** Technically supportable in Phase 1 but not a design target. No features are built to optimize for this case.

---

### Topology 3 — Multiple Humans, Multiple AIs (Canonical)

**Configuration:** 2+ humans (MCP) + 2+ AIs (API bridge), paired

Each human brings their own AI. Every feature in the design doc targets this topology.

**Sovereignty** means each participant controls their own model, key, budget, and system prompt. **Persistent autonomous conversation** means the AIs work between human sessions. **Convergence detection** catches the AIs agreeing too quickly. **Adversarial rotation** forces genuine evaluation rather than politeness spirals. **Routing modes** let each human independently calibrate engagement and cost. **Proposals** formalize decisions across participants. **Data security** keeps credentials isolated — each participant's API key is encrypted separately, accessible only to the API bridge for that participant's provider calls.

**Communication pattern in a typical session:**

```
Time    MCP Plane                    API Bridge Plane
─────   ─────────                    ────────────────
09:00   Human A connects             AI-A + AI-B in autonomous loop
09:05   Human A reads transcript     AI-A responds (turn 47)
09:06   Human A injects message      AI-B responds (turn 48, references A's injection)
09:07   Human A disconnects          Loop continues
...
14:30   Human B connects             AI-A responds (turn 112)
14:32   Human B reviews proposals    AI-B responds (turn 113)
14:33   Human B votes on proposal    Loop continues
14:35   Human B disconnects          Loop continues
...
22:00   (no humans connected)        AI-A responds (turn 184)
                                     Convergence detected (0.88 similarity)
                                     Divergence prompt injected
                                     AI-B responds (turn 185, challenges assumption)
                                     Similarity drops to 0.61
                                     Loop continues
```

**Phase alignment:** Phase 1 supports the 2+2 case (two humans, two AIs). Phase 3 scales to 5+5 with sub-session architecture for topic-scoped breakouts.

---

### Topology 4 — Asymmetric Participation (Mixed Human/AI)

**Configuration:** 2+ humans (MCP) + fewer AIs than humans (some participants have no AI)

Human A connects via MCP and has an AI in the conversation loop. Human B connects via MCP or Web UI and participates directly — reading, injecting messages, voting on proposals — but has no AI registered. Human B's record in the `participants` table has null or inactive provider configuration.

**This is distinct from Topology 2.** In Topology 2, one AI serves all humans. In Topology 4, Human A's AI represents Human A. Human B represents themselves. Sovereignty is preserved — Human B isn't borrowing anyone's AI. They're choosing not to run one.

**Use cases:**

A project manager works alongside a developer whose AI handles technical analysis. The PM reads the transcript, votes on proposals, and injects business constraints, but doesn't need or want to pay for an AI in the loop. Their participation is governance and direction, not generation.

A client reviews work that a consultant's AI is producing. The client's role is approval and steering. The consultant's AI does the heavy lifting. The client drops in, reads what the AI has drafted, provides feedback via message injection, and leaves.

A subject matter expert joins a session to answer specific questions. They don't need an AI — they *are* the expert. Other participants' AIs can address them by name (triggering `addressed_only` behavior for participants who have AIs), and the expert responds directly.

**Architectural behavior:** The turn router skips participants with no active AI. Human B's messages enter via the interrupt queue, tagged as human interjections with high priority. The conversation loop runs between whatever AIs are present. If only one AI is present (Human A's), the loop effectively becomes a single-AI session with multiple human participants — but with the AI clearly representing Human A, not serving as a shared resource.

Human B's `routing_preference` defaults to `human_only`, though this is a description of their behavior rather than a configuration the router acts on — the router already skips them because they have no AI to invoke.

**Schema representation:**

```
participants table:
┌─────────────┬──────────┬──────────┬──────────────────┬───────────────┐
│ participant │ role     │ provider │ model            │ routing_pref  │
├─────────────┼──────────┼──────────┼──────────────────┼───────────────┤
│ human_a     │ particip │ anthropic│ claude-opus-4-6  │ always        │
│ human_b     │ particip │ NULL     │ NULL             │ human_only    │
│ human_c     │ facilit  │ openai   │ gpt-4o           │ review_gate   │
└─────────────┴──────────┴──────────┴──────────────────┴───────────────┘
```

**Phase alignment:** Phase 1 supports this with minimal work. The participant schema already accommodates nullable provider fields. The turn router already skips participants based on routing mode. No new components are required.

---

### Topology 5 — Fully Autonomous (No Humans Connected)

**Configuration:** 0 humans (MCP) + 2+ AIs (API bridge)

No human is actively connected. The AIs run the conversation loop entirely on their own.

**This is not a separate configuration.** It's the steady state of Topology 1 or 3 when all humans close their clients. The design doc's §2.2 explicitly describes this: "When all humans close their clients and walk away, the AIs continue working — discussing open questions, evaluating options, refining proposals, identifying issues."

The architectural question is whether SACP should support sessions that *start* with no human present and *never* have a human connect. A scheduled session, launched by an API call or cron job, where two AIs work through a defined problem statement and produce a transcript for later human review.

**The architecture supports it.** The facilitator configures the session, approves AI participants, seeds an initial prompt or problem statement, and disconnects (or never connects). The conversation loop runs. Budget caps, convergence detection, circuit breakers, and per-turn timeouts provide automated guardrails. The facilitator reviews the transcript later via MCP or Web UI.

**The risk is runaway cost and quality drift.** Without a human to notice the AIs have gone off the rails, the only safeguards are automated. Convergence escalation pauses the loop and waits for human input — input that never comes if no human is monitoring. Budget caps are the hard financial stop. Circuit breakers catch provider failures. But there's no mechanism to catch an AI producing confidently wrong output that doesn't trigger any detector.

**Design implications for first-class support:**

If this topology is promoted from emergent behavior to an explicit mode, it needs additional guardrails beyond what Topologies 1–4 require:

`max_autonomous_turns` — a session-level cap that pauses the loop after N turns without human interaction. Prevents unbounded cost accumulation and quality drift.

`max_autonomous_cost` — a total spend ceiling (across all participants) that pauses the loop when reached. Distinct from per-participant budget caps, which protect individual participants but don't cap the session's total.

`notification_webhook` — a URL that receives POST requests when the loop pauses for any reason (convergence escalation, budget cap, circuit breaker, autonomous turn cap). Without this, a paused autonomous session sits indefinitely with no one aware it stopped.

`session_brief` — a structured initial prompt seeded into the conversation before the loop starts. In human-present topologies, the facilitator's first injection serves this purpose. In fully autonomous mode, it needs to be defined at session creation time.

**Phase alignment:** Emergent in Phase 1 (nothing prevents all humans from disconnecting). First-class support with the guardrails above would be a Phase 2 or Phase 3 addition, alongside the notification infrastructure the Web UI already requires.

---

### Topology 6 — Single Human, Single AI

**Configuration:** 1 human (MCP) + 1 AI (API bridge)

One person, one AI, no autonomous loop. This is a standard Claude Desktop or ChatGPT conversation with extra infrastructure in the way.

**Assessment: Not worth supporting.** The orchestration layer — turn router, convergence detector, adaptive cadence, adversarial rotation, routing modes, interrupt queue, cost tracker, summarization checkpoints — is designed for multi-participant dynamics. With one AI and one human, every component either does nothing or adds latency to what should be a direct conversation.

The MCP server adds a network hop between the human and the AI that doesn't exist in a direct client connection. The conversation state manager duplicates what the AI provider's own conversation history already handles. The API bridge translates messages through LiteLLM when the human could call the provider directly.

Use Claude Desktop, Claude Code, or any native client. SACP adds nothing here.

**Phase alignment:** Not a design target in any phase.

---

### Topology 7 — Client-Side AI / MCP-to-MCP

**Configuration:** 2+ humans with AI clients (all MCP inbound) + 0 AIs on the API bridge

Both participants connect to the orchestrator via MCP using AI-native desktop clients — Claude Desktop, a future ChatGPT desktop equivalent, or any MCP-capable AI client. Each participant's AI runs client-side and interacts with the shared conversation through MCP tools (`get_history`, `get_summary`, `inject_message`). The API bridge plane carries no traffic. The orchestrator never calls any AI provider.

This is a fundamentally different operating mode from Topologies 1–5. The orchestrator drops from "conversation loop driver" to "shared state manager and message broker."

```
               MCP Plane ONLY (all inbound)
               ────────────────────────────

Human A ──┐                                    ┌── Claude (runs inside
 Claude   │                                    │   Desktop client, calls
 Desktop  ├──MCP──▶ SACP Orchestrator          │   Anthropic API directly)
          │              │                     │
          │         PostgreSQL 16              │   API key stays on
          │         (canonical state)          │   Human A's machine
          │                                    └──────────────────────
Human B ──┤                                    ┌── GPT-4 (runs inside
 ChatGPT  │                                    │   Desktop client, calls
 Desktop  ├──MCP──▶ (same orchestrator)        │   OpenAI API directly)
          │                                    │
          │                                    │   API key stays on
          └────────────────────────            │   Human B's machine
                                               └──────────────────────

          No API Bridge Plane.
          Orchestrator makes zero AI provider calls.
```

**What the orchestrator retains:**

Conversation state management — the canonical transcript lives in PostgreSQL. Every `inject_message` call appends to the shared history. Both AIs read from the same source of truth via `get_history` and `get_summary`.

Authentication and governance — bearer tokens, facilitator role, participant approval, removal, audit log. The session governance model works identically.

Proposal workflow — `propose_decision` and `vote_decision` still operate through MCP tools. Decisions are recorded in the shared state.

Export — the transcript is still in PostgreSQL, so `export_session` works as designed.

Summarization checkpoints — the orchestrator can still trigger summarization on the stored transcript, though the summaries are consumed by MCP tool calls rather than injected into API bridge context assembly.

**What the orchestrator loses:**

The autonomous conversation loop. The orchestrator cannot "call" an AI — it can only wait for AI clients to poll via `get_history` or subscribe via SSE events. If both humans close their laptops, the conversation stops. There is no persistent autonomous operation. This is the single largest architectural difference from Topologies 1–5 and the primary tradeoff of maximum sovereignty.

Turn management and routing. The orchestrator has no turn counter, no round-robin, no routing mode enforcement. Both AIs can inject at any time. Turn ordering is first-come, first-served based on when `inject_message` calls arrive. The orchestrator can enforce rate limiting (preventing one client from flooding), but it cannot enforce "it's your turn now."

System prompt control. The orchestrator cannot inject system prompts, prompt tier instructions, adversarial rotation directives, or divergence prompts into the AI's context. Each AI's behavior is entirely controlled by its local client configuration and whatever the human has set up in their own system prompt. The 4-tier delta-only prompt architecture does not apply.

Context assembly. Each AI client is responsible for assembling its own context from the transcript data returned by `get_history` and `get_summary`. The orchestrator's 5-priority adaptive context algorithm is irrelevant — the orchestrator doesn't build prompts in this mode. Context window management quality depends entirely on the client AI's native conversation handling.

Response quality checks. The orchestrator cannot inspect responses before they enter the conversation. In the API bridge model, the orchestrator checks for empty responses, repetitive n-grams, framing breaks, and response size violations before logging to the database. In MCP-to-MCP mode, the `inject_message` call carries the final content — the orchestrator can still apply input validation (character limits, injection pattern filtering per §7.5), but cannot evaluate whether the response is empty, repetitive, or degenerate relative to prior turns.

Convergence detection. The orchestrator can still compute embeddings on messages stored in PostgreSQL and track similarity over a sliding window. But it cannot act on the results the same way. In API bridge mode, convergence triggers a divergence prompt injected into the next AI's system context. In MCP-to-MCP mode, the orchestrator can only flag convergence as a system event visible in the transcript — the AI clients would need to check for these flags and adjust their own behavior, which requires client-side cooperation.

Adversarial rotation. Impossible. The orchestrator cannot modify an AI's instructions between turns. Any adversarial prompting would need to be self-directed by the client's own system prompt configuration.

Cost tracking. Opaque. The orchestrator sees no API calls and receives no token counts. It can count characters in injected messages as a rough proxy, but has no visibility into actual token usage, model costs, or budget consumption. Per-participant budget enforcement is not possible without client self-reporting.

Adaptive cadence. No mechanism. The orchestrator cannot control turn delay. AIs respond whenever their human triggers them or whenever the client's own automation decides to poll.

**The sovereignty tradeoff:**

This topology maximizes sovereignty to its logical extreme. API keys never leave the participant's machine. The orchestrator has zero access to provider credentials. No Fernet encryption is needed for API keys because the orchestrator never sees them. No `update_api_key` MCP tool is needed. The `api_key_encrypted` column in the participants table is null for all participants.

The cost is loss of autonomous operation and loss of orchestrator-mediated quality control. The orchestrator becomes a shared clipboard with governance — a message board that two AI clients read from and write to, with authentication, proposals, and export layered on top.

**When this topology is worth the tradeoff:**

High-trust, high-security contexts where participants refuse to share API keys with any third-party infrastructure, even encrypted. Two security researchers who want a shared conversation record without exposing credentials. Two organizations evaluating a partnership where neither will provision API access to the other's systems.

It also works for ad-hoc, low-ceremony collaboration. Two people who already have Claude Desktop configured just add the SACP MCP server to their client config and start talking. No API key exchange, no registration beyond the auth token, no budget configuration. The barrier to entry is lower than any other topology.

**Potential enhancement — client-side protocol:**

If this topology graduates from "supported but limited" to a first-class mode, a lightweight client-side protocol could recover some of the lost capabilities. The orchestrator could publish "directives" as system events in the transcript — convergence warnings, adversarial prompts, turn suggestions — and compliant AI clients could incorporate these into their own context assembly. This is cooperative rather than enforced: a non-compliant client can ignore directives. But it would let convergence detection and adversarial rotation function in a best-effort mode.

A `report_usage` MCP tool could let clients self-report token counts and costs, restoring cost tracking visibility without requiring the orchestrator to make API calls.

Neither of these requires orchestrator-side API bridge functionality. They extend the MCP tool surface to recover capabilities through client cooperation rather than server control.

**Phase alignment:** Supportable in Phase 1 with no additional work — the MCP server and PostgreSQL state manager already handle `inject_message`, `get_history`, `get_summary`, and the proposal workflow. The orchestrator simply doesn't start the conversation loop engine for sessions with no API-bridge participants. First-class support with client-side protocol directives and `report_usage` would be Phase 3 or later.

---

## 3. Topology Comparison Matrix

| Property | T1: Solo+Multi-AI | T2: Multi-Human+1AI | T3: Canonical | T4: Asymmetric | T5: Autonomous | T6: 1+1 | T7: MCP-to-MCP |
|---|---|---|---|---|---|---|---|
| Humans (MCP) | 1 | 2+ | 2+ | 2+ | 0 | 1 | 2+ |
| AIs (API bridge) | 2+ | 1 | 2+ | 1+ (partial) | 2+ | 1 | 0 (client-side) |
| Sovereignty preserved | Partial (1 owner) | No | Yes | Yes | N/A | N/A | Maximum |
| Autonomous loop | Yes | Degenerate | Yes | Yes (reduced) | Yes | No | No |
| Convergence detection | Active | Meaningless | Active | Active if 2+ AIs | Active | N/A | Passive (flag only) |
| Adversarial rotation | Active | Meaningless | Active | Active if 2+ AIs | Active | N/A | Not possible |
| Routing modes useful | Yes | No | Yes | Partially | No humans to route | No | No (no turn control) |
| Model heterogeneity | Yes | No | Yes | Partial | Yes | No | Yes (client-side) |
| Budget independence | Yes (same owner) | No (shared) | Yes | Yes | Yes | N/A | Maximum (opaque) |
| Cost tracking | Orchestrator | Orchestrator | Orchestrator | Orchestrator | Orchestrator | N/A | Client self-report only |
| SACP value | High | Low | Maximum | High | Medium | None | Medium-High |
| Phase 1 support | Direct | Incidental | Direct | Direct | Emergent | Not targeted | Incidental |

---

## 4. Design Targets vs. Incidental Support

SACP's component inventory maps directly to the topologies that justify it.

**Components that require 2+ AIs to function:**

Convergence detection (embedding similarity across different speakers), adversarial rotation (rotating the contrarian role across participants), model heterogeneity as a feature (different reasoning patterns producing different perspectives), response format normalization (reconciling Claude's prose with GPT-4's markdown), capability registry and tool proxy (handling asymmetric tool calling support across models).

These components are active in Topologies 1, 3, and 5. They are inert or meaningless in Topologies 2, 4 (with 1 AI), and 6.

**Components that require 2+ humans to function:**

Proposal/vote workflow (multiple stakeholders reaching agreement), review-gate mode (human approval before AI response enters conversation), facilitator governance model (admin authority over other participants), data security policy (isolating credentials across participants), asymmetric context optimization (different context window sizes per participant).

These components are active in Topologies 3, 4, and partially in 2. They are single-user in Topologies 1 and 5, and unnecessary in 6.

**Components that function across all multi-participant topologies:**

Interrupt queue, adaptive cadence, cost tracking, summarization checkpoints, session lifecycle (archive/export/fork), MCP tool interface, conversation state manager, API bridge with LiteLLM.

**Components that function differently in Topology 7 (MCP-to-MCP):**

The conversation state manager, proposal workflow, authentication, governance, and export all function identically — they operate on data stored in PostgreSQL regardless of how it got there. Convergence detection can still compute embeddings on stored messages but can only flag results as system events rather than injecting divergence prompts. Summarization checkpoints can still be generated but are consumed by `get_summary` MCP calls rather than by the orchestrator's context assembly. Cost tracking, adaptive cadence, turn routing, adversarial rotation, response quality checks, system prompt control, and context assembly all cease to function because they require the orchestrator to make or control AI provider calls.

---

## 5. Implications for Phase 1

Phase 1 targets a 2-participant session. The topologies this enables:

**Topology 1** (1 human + 2 AIs) — fully supported. The facilitator registers two AI participants and monitors/steers via MCP.

**Topology 3** (2 humans + 2 AIs) — fully supported. Each participant brings their own AI. This is the canonical MVP test case.

**Topology 4** (2 humans + 1 AI) — supported with no additional work. One participant registers with a provider and model; the other registers with null provider and `routing_preference: human_only`.

**Topology 5** (0 humans + 2 AIs) — emergent. Nothing in Phase 1 prevents both humans from disconnecting. The loop continues until budget caps, convergence escalation, or circuit breakers pause it. No notification mechanism exists in Phase 1, so a paused autonomous session will sit unnoticed until a human reconnects.

No Phase 1 work is needed to support Topologies 2 or 6, and none should be done — they're outside SACP's value proposition.

**Topology 7** (2+ humans with AI clients, MCP-to-MCP) — incidentally supportable. The MCP server already handles `inject_message`, `get_history`, `get_summary`, and the proposal workflow. If no API-bridge participants are registered, the conversation loop engine simply has nothing to drive. The session becomes a shared state store that AI clients read from and write to. No additional Phase 1 work is required for basic operation. First-class support with client-side protocol directives would come later.

---

## 6. Open Questions

**Topology 5 promotion timeline.** Fully autonomous sessions are an interesting capability that falls naturally out of the architecture. The guardrails needed for first-class support (autonomous turn caps, session-level cost ceiling, notification webhooks, session briefs) overlap with Phase 2's Web UI notification infrastructure. Should these be bundled with Phase 2, or broken out as a separate feature spec?

**Topology 4 schema validation.** Should the orchestrator enforce that at least one AI is registered before starting the conversation loop? Currently nothing prevents a session with two `human_only` participants and zero AIs — a valid but useless configuration. A startup validation check (`assert count(participants where provider IS NOT NULL) >= 1`) would catch this without adding schema complexity.

**Hybrid topology transitions.** A session can move between topologies during its lifetime. Topology 3 becomes Topology 5 when both humans disconnect. Topology 4 becomes Topology 1 if the human-only participant disconnects. The orchestrator handles these transitions implicitly — the loop continues with whatever AIs are registered regardless of human connection state. Should topology transitions be logged as system events for audit purposes?

**Topology 7 client-side protocol.** If MCP-to-MCP becomes a first-class mode, the orchestrator needs a way to publish directives (convergence warnings, adversarial prompts, turn suggestions) that compliant AI clients can voluntarily incorporate. This requires defining a directive schema, an SSE event type for pushing directives to connected clients, and a contract for what "compliance" means. The design question is whether this protocol is SACP-specific or whether it should align with an emerging standard (MCP notifications, A2A signals). A `report_usage` MCP tool for client-side cost reporting is a simpler addition that could ship independently.

**Topology 7 hybrid mode.** A session could mix API-bridge participants and MCP-to-MCP participants simultaneously — one AI driven by the orchestrator's loop, another running client-side. This introduces coordination complexity (the loop-driven AI takes turns on schedule; the client-side AI injects asynchronously) but would let participants choose their sovereignty level independently. This is an architectural question worth resolving before Phase 3.
