# Building a multi-LLM orchestrator: eight hard problems and how to solve them

No single framework solves all eight challenges well — LiteLLM handles provider abstraction, LangGraph handles state, Strands handles streaming architecture, and each leaves the others to you. This report documents the practical patterns, model capabilities, and framework tradeoffs for each problem area.

---

## 1. System prompts degrade before they hit token limits

There is no separate "system prompt limit" — system prompts consume tokens from the total context window. Claude models offer **200K tokens** (1M in beta/GA as of early 2026), GPT-4o provides **128K**, and Llama 4 Scout reaches **10M tokens**. In theory, you could write an enormous system prompt for any of these. In practice, quality collapses long before you exhaust the window.

The research paper "Same Task, More Tokens" (Levy, Jacoby, Goldberg, 2024) found that **LLM reasoning performance starts degrading at roughly 3,000 tokens** — far below any model's technical maximum. A 2025 Chroma study testing 18 models, including GPT-4.1, Claude 4, and Gemini 2.5, found progressive accuracy decay at every context length increment, even on trivial tasks. The "lost in the middle" effect compounds this: models retrieve information best from the beginning or end of long inputs, with **20–30% performance drops** for information buried in the middle (Liu et al., 2023). The practical recommendation is to budget system prompts at **500–1,500 tokens**, placing critical instructions at the beginning and end.

The deeper portability challenge is **chat template divergence** across open-source models. Proprietary APIs (OpenAI, Anthropic, Google) handle formatting internally — you pass a `role: "system"` message and the provider handles the rest. Open-source models require model-specific special tokens. Llama 3.x uses `<|start_header_id|>system<|end_header_id|>`, Llama 4 simplified this to `<|header_start|>system<|header_end|>`, Mistral V1 uses `[INST]`/`[/INST]` as literal strings (V2+ makes them control tokens), and ChatML-based models (Qwen, OpenHermes) use `<|im_start|>system`. Using the wrong template causes severe performance degradation. HuggingFace's `tokenizer.apply_chat_template()` is the canonical solution for local models.

**LiteLLM** is the most widely adopted abstraction layer, translating OpenAI-format messages to provider-specific formats across 100+ providers. It auto-detects templates for known models and supports custom template registration via `litellm.register_prompt_template()`. For models that don't support system messages natively, LiteLLM falls back to prepending the system prompt to the first user message. Its `/utils/transform_request` endpoint lets you inspect exactly what gets sent to each provider — essential for debugging cross-model prompt issues.

Best practices for portable system prompts: use Markdown headers and XML tags (understood across models), avoid model-specific formatting tricks, keep instructions under 1,500 tokens, move reference material to RAG retrieval, and always test per model — prompt format transferability between model families is empirically very low, so per-model testing is mandatory.

---

## 2. Response format normalization requires structured output enforcement

Models differ dramatically in default output style. **GPT-4o** aggressively uses Markdown formatting — headers, bold text, bulleted lists, and code blocks appear even without explicit instructions. **Claude** is more restrained; Anthropic's internal system prompt actively discourages excessive Markdown and ordered lists. **Mistral Large** tends toward verbose explanations, while open-source models produce variable formatting depending on their fine-tuning data. These differences become critical when responses flow between agents in an orchestrator.

The most reliable normalization strategy is **structured output enforcement**, but support varies by provider:

| Provider | JSON Mode | Schema Enforcement | Mechanism |
|---|---|---|---|
| OpenAI | ✅ Native | ✅ `json_schema` in `response_format` | Constrained decoding |
| Anthropic | Via prompting | Via tool-use trick | Force model to "call" a tool with the desired schema |
| Google Gemini | ✅ `response_mime_type` | ✅ `response_schema` | Native schema enforcement |
| Mistral | ✅ API parameter | Limited | JSON mode only |
| Ollama/vLLM | ✅ `format: "json"` | Via grammar/outlines | Constrained decoding engines |

A September 2025 benchmark (DSPy.rb) found that **GPT-4o structured outputs** are fastest (1.77s) and 41–43% cheaper than prompting, while **Gemini 2.5 Flash** achieves the lowest cost ($0.000050/extraction) with 61% fewer tokens. For Anthropic, enhanced prompting (putting the JSON schema in the prompt) is actually **12–22% cheaper** than the tool-use trick due to overhead.

For a multi-LLM orchestrator, the practical pattern is a **three-tier normalization strategy**. First, use native schema enforcement where available (OpenAI's `json_schema`, Gemini's `response_schema`). Second, use the tool-use workaround for Claude (define a tool matching your desired output schema and force the model to call it). Third, fall back to prompt-based JSON instructions with client-side validation for models that support neither. Libraries like **Instructor** unify this across 15+ providers with Pydantic models, automatically selecting the best enforcement mechanism per provider. LiteLLM's `supports_response_schema()` helper lets you dynamically check what each model supports at runtime.

---

## 3. Tool calling works everywhere but works reliably almost nowhere

Native tool/function calling is now supported by all major providers, but the **format differences are significant**. OpenAI wraps tools in `{"type": "function", "function": {...}}` and returns arguments as JSON strings. Anthropic uses flat objects with `input_schema` and returns arguments as parsed objects. Google Gemini uses `function_declarations` arrays. Tool results go back as `role: "tool"` messages in OpenAI, but as `role: "user"` messages with `tool_result` content blocks in Anthropic. These differences mean the orchestrator must maintain a bidirectional translation layer.

The conversion itself is straightforward — the schemas are structurally similar:

```python
# OpenAI → Anthropic
{"name": t["function"]["name"],
 "description": t["function"]["description"],
 "input_schema": t["function"]["parameters"]}
```

The harder problem is **reliability across model sizes**. The Berkeley Function Calling Leaderboard (BFCL) V4 shows that top-tier models (GPT-4o, Claude Sonnet, Gemini) handle single-turn calls well but struggle with multi-turn and long-horizon tool use. Small models are far worse: **Llama 3.1 8B achieves ~91% accuracy** on function calling benchmarks, Mistral 7B hits ~86%, and both frequently fail on parallel tool calls or complex multi-tool scenarios. Specialized fine-tuned models like **Hammer-7B** and **ToolACE-8B** can rival GPT-4 on function calling despite their size, making them strong candidates for a tool-calling-focused local deployment.

For local model serving, **vLLM** offers the most production-ready tool calling — fully compatible with OpenAI's API, supporting parallel calls, `tool_choice` parameter, and guided decoding via Outlines for schema compliance. **Ollama** supports tool calling for tagged models (Llama 3.1+, Qwen 2.5, Mistral) but is less reliable with complex scenarios. LM Studio's support remains experimental with no streaming tool calls.

For models that don't support native function calling, the **ReAct pattern** (Thought → Action → Observation loop) described in the system prompt remains effective. LangChain's `create_react_agent` falls back to this automatically. The orchestrator should maintain a capability registry per model and route tool-heavy tasks to models with proven function calling reliability, falling back to prompt-based tool use for smaller or less capable models.

---

## 4. Context windows span three orders of magnitude, and stated sizes lie

The range of context windows across current models is enormous — from **8K tokens** (Llama 3 base) to **10M tokens** (Llama 4 Scout). Here are the key figures:

| Model | Context Window | Max Output |
|---|---|---|
| Llama 4 Scout | 10M | — |
| Gemini 1.5 Pro | 2M | 8K |
| Llama 4 Maverick / Gemini 2.5 Pro / Claude (1M beta) | 1M | varies |
| GPT-4.1 / GPT-4.1 mini | 1M | 32K |
| Mistral Large 3 | 256K | — |
| Claude 3.5 Sonnet / Claude 4 | 200K | 8K–64K |
| GPT-4o / Llama 3.1 / DeepSeek V3 / Qwen 2.5 | 128K | 16K |
| Mixtral 8x7B / Mistral 7B | 32K | — |

**Stated context ≠ effective context.** Testing consistently shows that most models "break much earlier than advertised." A model claiming 200K tokens typically becomes unreliable around 130K, with sudden performance drops. The "lost in the middle" phenomenon (Liu et al., 2023) creates a U-shaped performance curve where information at the beginning and end of context is retrieved well, but middle content suffers **20-30% accuracy drops**. Newer techniques like Ms-PoE (Multi-scale Positional Encoding) and Microsoft's IN2 training mitigate this, but the effect persists across all current architectures.

For practical conversation coherence, **16K–32K tokens** is the sweet spot for most use cases — sufficient for 10–20 detailed turns plus system prompt and tool definitions. Below 8K tokens, multi-turn coherence degrades noticeably.

The gold standard for context management is **MemGPT/Letta's OS-inspired memory hierarchy**: core memory (always in context, self-edited by the agent), a message buffer (sliding window of recent messages), recall memory (searchable conversation history via tool calls), and archival memory (long-term vector store). This architecture lets agents maintain coherent conversations over arbitrary lengths while staying within small context windows. Memory hierarchy approaches report 80–90% token cost reduction versus naive full-history approaches (A-Mem, arXiv:2502.12110, measured 85–93% reduction compared to MemGPT baselines).

For the orchestrator, the practical pattern is **adaptive context management** — pass full history to models with 1M+ context windows (Gemini, Claude extended, GPT-4.1), and apply progressive summarization for smaller models. LangChain provides `ConversationSummaryBufferMemory` (hybrid summarization + recent verbatim), while Strands offers `SlidingWindowConversationManager`. The critical implementation detail: **always place tool definitions and critical instructions at the beginning of context and recent conversation at the end**, exploiting the U-shaped attention curve.

Important Ollama caveat: self-hosted models default to **2,048 tokens** context regardless of the model's actual capacity. You must explicitly set `num_ctx` to use the full window.

---

## 5. Streaming demands a split-stream architecture with provider normalization

All major LLM providers use **Server-Sent Events (SSE)** for streaming, but their formats diverge. OpenAI streams tool calls with the function name in the first chunk and arguments as string deltas, ending with `data: [DONE]`. Anthropic uses explicit event types (`message_start`, `content_block_delta`, `content_block_stop`) that interleave text and tool call content blocks. Google Gemini streams via `streamGenerateContent?alt=sse` with chunks matching its non-streaming format. The orchestrator needs a **unified streaming adapter** that normalizes these into a single event protocol.

The fundamental architecture pattern is **dual streaming** — tokens must flow to the UI in real-time while simultaneously accumulating for orchestrator state management. The simplest implementation is an accumulator buffer:

```python
full_response = ""
for chunk in llm_stream:
    full_response += chunk.content  # Buffer for state
    yield chunk                      # Forward to UI
# full_response now available for state management
```

LangGraph offers the most sophisticated approach with **five simultaneous streaming modes**: `values` (full state snapshots), `updates` (state deltas), `messages` (token-level streaming), `custom` (user-defined events), and `debug`. These can be combined — streaming `messages` to the UI while capturing `updates` for the orchestrator — using the v2 format where every chunk carries a `type` field for discrimination.

Among frameworks, **Strands Agents** (AWS) was designed "streaming first" with all model interactions flowing through unified `StreamEvent` types and built-in cancellation support. **CrewAI's streaming has historically been weak** — despite community demand across 8+ GitHub issues, its multi-agent architecture makes clean token streaming difficult, though November 2025 updates improved this. **AutoGen/Microsoft Agent Framework** supports `model_client_stream=True` with `run_stream()` yielding chunks in real-time.

Two critical streaming challenges deserve attention. First, **tool calls mid-stream**: when a model decides to call a tool, the orchestrator should buffer the tool call data (it's small and not user-facing) rather than streaming raw JSON to the UI, execute the tool, then resume streaming the text response. Second, **parallel agent streaming**: SSE wasn't designed for multiplexing multiple agent outputs. The production pattern is tagged event streams where each chunk carries an agent identifier, allowing the UI to demultiplex and render multiple concurrent agent outputs.

---

## 6. LLM APIs fail in ways HTTP status codes don't capture

LLM API failures fall into two categories: **infrastructure failures** (rate limits, timeouts, server errors) and **quality failures** (degenerate output with a 200 OK status). Infrastructure failures are straightforward — retry with exponential backoff plus jitter, respect `Retry-After` headers, cap at 5–7 attempts with 60-second max delay. Provider-specific nuances matter: OpenAI had a **34-hour outage** in June 2025 (June 10–11), demonstrating that even major providers can experience extended downtime; Anthropic's 529 "Overloaded" errors can persist for hours during peak usage; Google Gemini can silently return unhelpful responses with 200 OK.

**LiteLLM provides the most comprehensive fallback system** in production. It supports ordered model fallback lists (try Claude, then GPT-4, then local model), context window fallbacks (automatically route to larger-context models on `ContextWindowExceededError`), content policy fallbacks (switch providers on safety rejections), and cooldown management for failed deployments. A real-world fallback chain from production: Anthropic Claude (primary) → OpenAI (secondary) → OpenRouter auto (catchall) → OpenAI direct API (last resort).

Quality failures are harder to detect. **Repetition loops** — where autoregressive generation creates positive feedback loops — are the most common degenerate mode. The SpecRA paper (2025) uses FFT-based autocorrelation to detect repetition across 813 samples from 1.13M agent outputs. A simpler production approach: monitor n-gram frequency during streaming, terminate when repetition is detected, and retry with adjusted temperature or a different provider. One practitioner reduced repetition from **15% to 0%** across 320+ tests primarily through prompt optimization — removing repetitive structures (numbered lists, parallel bullets) that teach the model to "continue counting."

The recommended architecture is a **three-layer defense**. Layer 1 (prevention): well-structured prompts with anti-repetition instructions. Layer 2 (detection): real-time stream monitoring for repeated n-grams, empty outputs, and off-topic responses — terminate and retry on detection. Layer 3 (fallback): post-processing truncation and provider switching. **NeMo Guardrails** handles output-level validation with a streaming mode that chunks responses for context-aware moderation, while **Guardrails AI** provides a hub of pre-built validators (toxicity, PII, structured data) with auto-correction capabilities.

The circuit breaker pattern completes the reliability stack: track failure rates per provider, "open" the circuit when failures exceed a threshold to give the provider time to recover, and periodically test with half-open requests. **Portkey** implements configurable circuit breakers that auto-remove unhealthy providers from routing.

---

## 7. MCP authentication evolved from "none" to full OAuth 2.1

The Model Context Protocol's auth story has matured rapidly across four specification versions. The initial November 2024 spec had **no formal authentication**. The March 2025 spec introduced Streamable HTTP transport with basic authorization. The June 2025 spec classified MCP servers as **OAuth 2.1 Resource Servers** with mandatory Protected Resource Metadata (RFC 9728) and Resource Indicators (RFC 8707). The November 2025 spec added **Client ID Metadata Documents (CIMD)** as the default registration mechanism, step-up authorization flows, and cross-app access for enterprise deployments.

Key architectural decisions: authorization is **optional** for MCP implementations. STDIO transports (local subprocess communication) should retrieve credentials from environment variables — they have no network attack surface. HTTP-based transports should implement the full OAuth 2.1 flow with PKCE (S256 mandatory). MCP clients must maintain separate credentials per authorization server and use resource parameters to bind tokens to specific servers, preventing cross-service token reuse.

Production implementations demonstrate several patterns. **Cloudflare Workers MCP** offers four approaches in a single template: Cloudflare Access SSO, third-party OAuth (GitHub/Google), running your own OAuth provider, and self-handled auth. **SageMCP** implements multi-tenant isolation with per-tenant WebSocket endpoints (`ws://host/api/v1/{tenant-slug}/mcp`), OAuth tokens per user, and token-bucket rate limiting. The **AWS multi-tenant MCP sample** uses Amazon Cognito with OAuth 2.1 for a B2B travel booking reference implementation.

For multi-user security, the Streamable HTTP transport uses `Mcp-Session-Id` headers (cryptographically secure UUIDs or JWTs) for session isolation. Each session maintains independent state. The step-up authorization flow (new in November 2025) enables **least-privilege access**: servers respond with 403 and required scopes when a tool needs elevated permissions, and the client re-authorizes with expanded scope. For enterprise deployments, the Cross App Access pattern integrates with corporate identity providers to eliminate OAuth consent screens.

The practical recommendation for a multi-LLM orchestrator: use **OAuth 2.1 with CIMD** for remote MCP servers, path-based or URL-based tenant isolation for multi-user deployments, JWT session IDs encoding user identity for cross-validation, and STDIO transport for local-only development tools. Always validate Origin headers on Streamable HTTP endpoints to prevent DNS rebinding attacks.

---

## 8. Conversation branching is LangGraph's killer feature, but few others support it

LangGraph is the only major framework with production-grade conversation branching and time travel. Its checkpointing system saves complete graph state at every super-step boundary, storing snapshots in threads with pluggable backends (PostgreSQL, SQLite, Redis). Time travel lets you replay from any prior checkpoint — `get_state_history()` browses all checkpoints, and `update_state()` on a prior checkpoint creates a new branch while preserving the original execution history. This enables "what-if" exploration: take a conversation to any point, modify state, and fork into an alternate timeline.

Other frameworks lag significantly. **CrewAI** offers task-level replay (re-run specific tasks) but no fine-grained checkpointing or branching. **AutoGen** maintains ephemeral in-memory conversation history with no formal state persistence. **Strands Agents** has minimal state management infrastructure with no time-travel features. **OpenAI's Agents SDK** provides only basic retries with no rollback semantics.

Two academic projects push the boundary further. **ContextBranch** (arXiv:2512.13914) is a lightweight Python SDK (~900 lines, zero dependencies) implementing four git-inspired primitives: `checkpoint` (immutable snapshot), `branch` (isolated context), `switch` (O(1) context swap), and `inject` (selective merge). Testing showed **2.5% higher quality** with 58.1% context size reduction. **Git-Context-Controller (GCC)** (arXiv:2508.00031) manages agent context as a version-controlled file system with COMMIT, BRANCH, MERGE, and CONTEXT commands, achieving **48% bug resolution on SWE-Bench-Lite** versus 43% for the next-best approach.

The **conversation tree data structure** pattern from Ably's AI Transport implementation is instructive for building this yourself. Every message is a node with a parent pointer, stored in three structures: a `nodeIndex` (ID → node map), a `sortedList` (serial-ordered for pagination), and a `parentIndex` (parent ID → child IDs). Edits create sibling nodes; regenerations create sibling responses. Nothing is ever deleted. A "flatten" algorithm walks from root following branch selections to produce a linear view for rendering. The database schema is simple: a `messages` table with `id`, `parent_id`, `thread_id`, `role`, `content`, and `serial`, plus a `branch_selections` table mapping parent messages to selected children.

For handling **irreversible side effects** (sent emails, API calls, database writes), the Saga pattern applies: each tool action records a compensating transaction, and on rollback, compensations execute in reverse order. LangGraph encodes this directly in the graph — failure nodes branch to compensating action edges. The key limitation: not all operations are truly reversible, so the orchestrator must classify tools as reversible or irreversible and warn users before branching past irreversible actions.

---

## Conclusion

No single framework covers all eight problems. LiteLLM handles provider abstraction for prompts, streaming, and errors but doesn't touch conversation branching. LangGraph handles state and branching but delegates provider normalization to LangChain's abstractions. Strands is streaming-first but has no time-travel features. The orchestrator is the integration point that fills the gaps between them.

Three decisions have outsized impact on the result. A per-model capability registry — tracking context window size, tool-calling reliability (BFCL), structured-output support, and streaming format — lets the orchestrator route by task requirements rather than convention. A split-stream accumulator at the core normalizes the three providers' SSE formats into a single event protocol while buffering complete responses for state management. And the message store should be tree-structured from day one: `id`, `parent_id`, `thread_id`, `role`, `content`, `serial`, plus a `branch_selections` table. Retrofitting a linear history into a tree later is painful; the schema is cheap to start with.

Context windows tripled in 2025, MCP auth went from nonexistent to full OAuth 2.1 in twelve months, and function calling landed on 7B local models. Pinning architecture to what any single provider does today is how you inherit their limitations. Keep it as a thin translation layer.
