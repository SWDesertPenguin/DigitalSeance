# SACP Use Cases

## Design Supplement

**Parent document:** `sacp-design.md` §1 (The Gap in the Current Landscape)
**Status:** Design supplement — concrete scenarios illustrating SACP's value proposition
**Scope:** Six use cases demonstrating where SACP fills a gap that existing tools cannot

---

## 1. Distributed Software Collaboration

Two developers work on a shared codebase from different machines, each with their own AI assistant that has accumulated project context through weeks of solo work. Developer A uses Claude with Vaire memory and a local codebase MCP server. Developer B uses GPT-4 with their own toolchain.

They spin up an SACP session. Both AIs enter the loop carrying their respective context. Developer A's Claude knows the auth subsystem intimately. Developer B's GPT-4 has been deep in the data layer. The AIs discuss integration points, surface contradictions in approach, and draft interface contracts — all while both humans are at work doing other things.

Developer A drops in over lunch, reads the transcript, sees the AIs have identified a race condition at the boundary between their subsystems. She injects a clarifying message about the locking strategy she prefers, then leaves. The AIs incorporate that constraint and continue refining.

The session uses `propose_decision` to formalize interface contracts. Both humans vote. Accepted proposals get stored to Vaire for persistent project memory.

**Why SACP and not existing tools:** CrewAI could orchestrate multiple agents on this problem, but both developers would need to hand their context and API keys to a single operator. There's no sovereignty, no independent budget control, and no persistent conversation that survives across work sessions.

---

## 2. Research Paper Co-authorship

Two researchers at different institutions are co-writing a paper. Each has been using their own AI to develop arguments, review literature, and draft sections. Researcher A runs Opus at max prompt tier for deep analytical work. Researcher B uses a local Llama model through Ollama to stay within a tight budget, running at low prompt tier.

The SACP session handles this asymmetry transparently. Researcher B's AI operates in `delegate_low` mode, skipping low-complexity turns. The context assembly pipeline sends Researcher B's model an aggressively summarized context window (3–5 recent turns) while Researcher A's Opus gets the full 30–50 turn window. Both AIs stay current on key decisions through the structured summarization checkpoints.

The AIs debate methodology, surface gaps in the argument, and draft section outlines. The adversarial rotation kicks in every 12 turns, preventing the politeness spiral where both AIs agree on a weak argument structure. When convergence detection flags that the AIs are circling the same framing, it escalates to the humans.

Researchers drop in asynchronously — different time zones, different schedules. Each reads the transcript, reviews proposals, injects guidance, and leaves.

**Why SACP and not existing tools:** Copilot Cowork gives both researchers access to one AI, but loses the individual context each has built. A shared Google Doc with AI assistance doesn't let the AIs work autonomously when the humans aren't present.

---

## 3. Consulting Engagement

A consultant brings their Claude-based AI (loaded with client industry context via MCP-connected knowledge bases) into a session with the client's internal AI (GPT-4, connected to the client's proprietary data through their own MCP servers). The client's data never leaves their control. The consultant's methodology stays in their own AI's context.

The client sets their AI to `review_gate` mode — every response their AI drafts gets staged for human approval before entering the conversation. The consultant runs in `always` mode. This means the consultant's AI responds freely while the client maintains approval authority over what their AI shares.

The session produces structured proposals for recommendations. The client's facilitator has full admin control — they can archive, remove the consultant's access, or revoke tokens at any time. The admin audit log records every governance action.

On export, the client gets a full transcript minus the consultant's system prompt content and detailed usage data. The data security policy ensures API keys are purged when the consultant disconnects.

**Why SACP and not existing tools:** The sovereignty model is the entire point here. No existing tool lets two parties collaborate through their respective AIs without one party surrendering their credentials or data access to the other's infrastructure.

---

## 4. Open Source Project Coordination

A maintainer and a contributor need to hash out an RFC for a new feature. The maintainer runs the SACP orchestrator (facilitator role) and sets session config with `complexity_classifier_mode: "embedding"` to route substantive design questions to both AIs while filtering boilerplate.

The contributor joins via invite link, provides their API key, and enters in `burst` mode — their AI stays silent for 10 turns, then synthesizes a comprehensive response. This keeps their costs low while still contributing meaningfully to the discussion.

The AIs work through edge cases, API surface design, and backward compatibility concerns. When they identify a decision point, they use `propose_decision`. The maintainer resolves proposals with facilitator override when needed.

After the session, `export_session(format: "markdown")` produces a clean transcript that becomes the basis for the RFC document. Accepted proposals export to Vaire as persistent project decisions.

**Why SACP and not existing tools:** The contributors don't share an organization, a platform subscription, or a budget. Each pays their own way (BYOK). The conversation persists across days of asynchronous work. No agent framework supports this participation model.

---

## 5. Technical Review and Audit

A security architect and a developer need to review a codebase for vulnerabilities. The architect's Claude is connected to NIST frameworks and threat intelligence via MCP. The developer's AI has the codebase loaded through a filesystem MCP server.

The architect sets their AI to `observer` mode — it reads every 5 turns and only speaks when it identifies a security concern. The developer's AI walks through the code in `always` mode, explaining architecture decisions and flagging areas of uncertainty.

When the architect's AI does speak, it references specific controls (AC-3, SI-10, SC-8) and maps findings to the threat model. The developer's AI responds with implementation details. The orchestrator's tool proxy handles the asymmetry — the developer's model doesn't have native tool calling, so `[NEED:]` requests get parsed and executed by the orchestrator.

Findings accumulate as proposals. The architect (facilitator) resolves each one with a severity classification. The exported session becomes the audit report.

**Why SACP and not existing tools:** Each participant's AI has access to different sensitive resources (threat intel vs. source code) through their own MCP connections. The orchestrator never sees the raw data — only the conversation. Sovereignty keeps the security boundary clean.

---

## 6. Decision-Making Under Asymmetric Expertise

A product manager and a data scientist are deciding on a recommendation algorithm. The PM's AI runs a smaller model in `addressed_only` mode (zero cost until mentioned by name), focused on business constraints and user experience. The data scientist's AI runs Opus in `always` mode, doing the heavy analytical work.

The data scientist's AI evaluates algorithm options, discusses tradeoffs between accuracy and latency, and proposes approaches. When it needs business input — "what's the acceptable cold-start degradation for new users?" — it addresses the PM's AI by name. The PM's AI activates, answers from its loaded product requirements, and goes back to sleep.

Both humans review proposals asynchronously. The PM votes based on business viability. The data scientist votes based on technical feasibility. Disagreements surface as rejected proposals with comments, forcing the AIs to find alternatives.

**Why SACP and not existing tools:** The routing modes make asymmetric participation a first-class feature rather than a hack. The PM isn't paying for 200 turns of algorithm discussion they don't care about. They pay only when their expertise is needed.

---

## 7. Zero-Trust Cross-Organization Collaboration

Two security teams at different organizations need to coordinate incident response for a shared supply chain vulnerability. Neither organization will provision API credentials to the other's infrastructure, and both have policies prohibiting API key storage on third-party systems.

Each team member runs their own AI desktop client — one uses Claude Desktop, the other uses an internal ChatGPT-based tool. Both connect to an SACP orchestrator (hosted by the coordinating organization) as an MCP server. Their AIs run entirely client-side. The orchestrator never sees an API key, never makes a provider call, never touches either organization's AI budget.

The conversation works through MCP tools. Each participant's AI calls `get_history` to read the shared transcript, processes it locally within their own client, and calls `inject_message` to contribute. The orchestrator stores the canonical transcript in PostgreSQL, handles authentication, and manages the proposal workflow.

When the teams identify a mitigation strategy, they formalize it with `propose_decision`. Both participants vote. The accepted proposal is exported as the coordination record.

The tradeoff: no autonomous conversation. When both participants close their laptops, the conversation stops. There's no overnight AI-to-AI analysis. The orchestrator can't enforce turn ordering, inject adversarial prompts, or detect convergence (though it can flag it passively). Both teams accept this tradeoff because the alternative — sharing API keys — is a non-starter.

**Why SACP and not existing tools:** The MCP-to-MCP topology gives both organizations a shared conversation record with authentication, governance, proposals, and export — without requiring either to expose credentials to external infrastructure. A shared Slack channel doesn't give them structured decision tracking. Email chains don't give them a canonical transcript. And no agent framework supports a mode where the orchestrator manages state without touching provider APIs.

---

## Common Properties

Six of the seven cases share the properties that define SACP's core niche: multiple independent participants who control their own AI, model choice, and budget; persistent conversation that runs without human presence; asynchronous human drop-in when it matters; no requirement to surrender credentials or data to a central operator; and distributed cost where each participant pays for their own AI's participation.

Use case 7 (cross-organization collaboration) trades persistent autonomous conversation for maximum sovereignty — the orchestrator never touches API keys at all. It demonstrates that SACP's shared state management, governance, and proposal workflow have value even without the autonomous conversation loop. The orchestrator serves as a governed message broker rather than a conversation driver.

No existing tool — agent framework, shared-AI workspace, or federation protocol — provides all of these properties simultaneously. Each use case exercises a different subset of SACP's capabilities, validating that the architecture's modularity lets components activate or deactivate based on the topology and configuration chosen by the participants.
