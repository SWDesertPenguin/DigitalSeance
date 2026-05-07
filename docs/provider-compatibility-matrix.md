# Provider Compatibility Matrix

LiteLLM is the abstraction SACP uses to dispatch requests to AI providers, but
each provider has quirks that the abstraction can mask rather than eliminate.
This document catalogues the per-provider behaviours operators need to know
about, plus the contract the local code keeps with each.

Sourced from the pre-Phase-3 audit window's cross-cutting "provider
compatibility matrix" review. Phase F deliverable from
`fix/provider-compat-matrix`.

---

## Supported providers (Phase 1)

| Provider | LiteLLM prefix | API key env shape | Cost source | Streaming endpoint |
|---|---|---|---|---|
| Anthropic | `anthropic/` | `sk-ant-...` (per-participant in DB) | LiteLLM model registry | `/v1/messages` SSE |
| OpenAI | `openai/` (default) | `sk-...` (per-participant) | LiteLLM model registry | `/v1/chat/completions` SSE |
| Google Gemini | `gemini/` | `AIza...` (per-participant) | LiteLLM model registry | `/v1beta/models/.../streamGenerateContent` |
| Groq | `groq/` | `gsk_...` (per-participant) | LiteLLM model registry | `/openai/v1/chat/completions` SSE |
| Ollama | `ollama_chat/` | NONE (local; `api_base` per-participant) | None — `cost_per_input_token` is null | `/api/chat` (note: `ollama/` prefix routes to `/api/generate` and is rewritten to `ollama_chat/` in `_normalize_ollama_model`) |

---

## Streaming vs non-streaming

| Provider | Steady-state stream framing | Stream finish signal | Notes |
|---|---|---|---|
| Anthropic | SSE with `event: content_block_delta` then `event: message_stop` | `message_stop` event | `index` field disambiguates parallel content blocks (tool use). |
| OpenAI | SSE `data: {...}\n\ndata: [DONE]\n\n` | literal `[DONE]` payload | `data:` line carries `delta.content` until done. |
| Gemini | NDJSON-style chunks (no `data:` prefix) | empty chunk OR `finishReason` field | LiteLLM normalises to OpenAI-compatible deltas. |
| Groq | OpenAI-compatible SSE | `[DONE]` | OpenAI-compatible by design; same framing. |
| Ollama | NDJSON: one JSON object per line, `done: true` on final | `done: true` | Local; latency is dominated by token-generation speed, not network. |

Phase 1 does NOT use streaming on the orchestrator dispatch path
(`src/api_bridge/provider.py:_call_litellm` calls `acompletion`, not
`acompletion(stream=True)`). LiteLLM still buffers the full response. This
table is informational for Phase 3 streaming-dispatch work.

---

## Error-code translation

| Surface | Anthropic | OpenAI | Gemini | Groq |
|---|---|---|---|---|
| Rate-limit | `429 rate_limit_error` | `429 rate_limit_exceeded` | `429 RESOURCE_EXHAUSTED` | `429 rate_limit_exceeded` |
| Auth invalid | `401 authentication_error` | `401 invalid_api_key` | `401 PERMISSION_DENIED` | `401 invalid_api_key` |
| Quota exhausted | `429` (rare; usually rate-limit shape) | `429 insufficient_quota` | `429 RESOURCE_EXHAUSTED` (zero-quota free tier) | `429` |
| Server error | `500` / `529 overloaded_error` | `500` / `503` | `500 INTERNAL` | `500` |
| Bad request | `400 invalid_request_error` | `400 invalid_request_error` | `400 INVALID_ARGUMENT` | `400` |

LiteLLM normalises most of the above into `litellm.RateLimitError`,
`litellm.AuthenticationError`, `litellm.APIError`, etc. The orchestrator
catches `litellm.RateLimitError` for retry (`provider.py:dispatch_with_retry`)
and lets everything else bubble as `ProviderDispatchError`.

---

## Rate-limit headers

| Provider | Header | Format | LiteLLM exposure |
|---|---|---|---|
| Anthropic | `anthropic-ratelimit-tokens-reset` | ISO-8601 | Surfaced via response headers when raising RateLimitError. |
| OpenAI | `Retry-After` (RFC 7231 delta-seconds) | integer or HTTP-date | Surfaced as RateLimitError attribute. |
| Gemini | `retry-delay` in error body (`error.details[].retryDelay`) | seconds (e.g., `42s`) | Surfaced via the error message string. |
| Groq | `Retry-After` | integer | OpenAI-compatible. |

The orchestrator's `_backoff_delay` uses an exponential schedule
(1s / 2s / 4s + jitter) and does NOT yet honour provider-specific
`Retry-After` values. Phase 3 enhancement: parse the header and clamp
the exponential delay to the provider's stated reset time.

---

## max_tokens semantics

| Provider | `max_tokens` interpretation |
|---|---|
| Anthropic | Hard cap on output tokens; required by the API. |
| OpenAI | Hard cap on output tokens; truncates response if reached. |
| Gemini | Soft cap; some models continue past it. |
| Groq | OpenAI-compatible hard cap. |
| Ollama | Optional; behaviour depends on model. |

The orchestrator passes `max_tokens` only when the participant has
`max_tokens_per_turn` configured (see `provider.py:_call_litellm`).

---

## Cost-calculation accuracy

LiteLLM ships a model-pricing registry that updates with each LiteLLM
release. The orchestrator calls `litellm.completion_cost(...)` to
compute `cost_usd` per response. Known caveats:

- **Pricing lag**: LiteLLM may lag actual provider price changes by
  one or more releases. Operators should track `litellm`'s changelog.
- **Custom / local models**: Ollama and self-hosted models return
  `cost = 0.0` because `completion_cost` raises and the orchestrator
  swallows the exception (see `_compute_cost`). Budget enforcement
  treats these as free, which is correct for local infra but wrong
  for self-hosted clouds where compute has a real cost. Phase 3 may
  expose `cost_per_input_token` / `cost_per_output_token` overrides
  on the participant record so operators can attribute self-host cost.
- **Cost None vs 0.0**: Participants with `cost_per_input_token = None`
  rank last in the summarizer's cost-sort (`_cost_key` returns +inf).
  `cost_usd = 0.0` returns reach the budget enforcer as zero; this is
  by-design (Ollama is treated as free).

---

## Tool-use / function-calling support

| Provider | Tool-use support | Phase 1 use |
|---|---|---|
| Anthropic | Yes (Claude 3.5+) | Not used; SACP routes via plain text messages. |
| OpenAI | Yes (`tools` API) | Not used; same. |
| Gemini | Yes (function declarations) | Not used. |
| Groq | OpenAI-compatible | Not used. |
| Ollama | Model-dependent | Not used. |

Phase 3+ may introduce tool-use for orchestrator-issued helper calls
(e.g., search, calculator). Today the orchestrator is text-only.

---

## Context-window numbers (truncation surface)

LiteLLM exposes `litellm.get_max_tokens(model)` which returns the
provider-published context window. SACP uses this implicitly via
LiteLLM's truncation logic. Known mismatches:

- **Claude Sonnet 4.6 / Sonnet 4.5**: ~200K context window;
  LiteLLM's registry tracks correctly.
- **Gemini 2.0+**: ~1M-2M context window; LiteLLM tracks but
  practical bottleneck is per-request cost on long contexts.
- **GPT-4o / GPT-4.1**: ~128K context window.
- **Groq Llama models**: 32K-128K context window depending on
  variant.
- **Ollama local**: depends on the loaded model and the Ollama
  server's `num_ctx` setting; LiteLLM does NOT introspect this.

When an operator selects a model whose context window LiteLLM
under-reports, the orchestrator may send a request that the provider
silently truncates, producing a coherent-looking but partial response.
Phase 3 may introduce a context-window-budget cross-check at message
assembly time.

---

## Ollama local quirks

- **Tokenization**: Ollama uses model-specific tokenizers
  (Llama uses tiktoken-compatible; Mistral uses sentencepiece). LiteLLM
  approximates token counts via heuristics; precise counts require
  pulling tokenizer libraries the orchestrator does not ship.
- **Cost is null**: `cost_per_input_token` and `cost_per_output_token`
  are null for Ollama participants. Budget enforcement treats them as
  free; the summarizer cost-sort ranks them last.
- **Model availability**: Operator-controlled. `list_provider_models`
  cannot enumerate Ollama models (no central registry); operators must
  configure each `model` per-participant.
- **Streaming endpoint quirk**: LiteLLM's `ollama/` prefix routes to
  `/api/generate` which streams by default and times out with httpx.
  `ollama_chat/` prefix routes to `/api/chat` which is what SACP wants.
  `_normalize_ollama_model` rewrites the prefix automatically.

## Groq specific behaviours

- **Very fast inference**: Groq's TPS can exceed downstream consumer
  rate limits. A SACP session with a Groq participant may hit the
  participant's own rate-limit (60 req/min default) faster than other
  providers. Operators tuning aggressive cadence should account for
  this.
- **Token-counting accuracy**: Groq returns `usage` fields compatible
  with OpenAI shape; cost calculation matches.

## Gemini 2.x quota issues

- **Free-tier zero-quota**: Fresh free-tier API keys can hit zero
  quota immediately on creation (documented in operational memory).
  The model picker filter blocklists known-zero-quota models so they
  don't get selected.
- **Per-project rate limits**: Gemini's quota is per-project
  (i.e., shared across all keys in a Google Cloud project), not
  per-key. Two participants using different keys from the same
  project share the rate-limit pool.

## Provider-deprecation handling

Providers occasionally deprecate model IDs; the upstream API may
return a `deprecation` HTTP header (or a 410 status, or a 400 with a
"deprecated" error string — non-uniform). LiteLLM does NOT normalise
deprecation signals into a single shape. Today there is no spec'd
behaviour: an operator running a deprecated model just sees errors
in their logs.

Phase 3 trigger: when LiteLLM ships a normalised deprecation event,
SACP should add a `provider_deprecation` security_events row + a
operator-notification path mirroring 007 §FR-016.

## Multi-key same-model AIs

Two participants using the same `model` with different `api_key`
values should NOT share LiteLLM cache state. Round07 surfaced a bug
where LiteLLM cached the first-seen API key and re-used it for
subsequent calls to the same model — fixed upstream. The orchestrator
explicitly passes `api_key=` per call so the cache key includes the
key.

## Per-provider regression test fixtures

`tests/fixtures/provider_stubs.py` provides synthetic LiteLLM stubs
that simulate each provider's specific error / rate-limit / streaming
behaviour. Tests in `tests/test_provider_compat_matrix.py` exercise:

- Rate-limit error normalisation per provider
- Auth-error normalisation per provider
- Cost-calculation fallback for null-cost (Ollama)
- max_tokens passthrough behaviour
- Ollama prefix normalisation

The stubs are intentionally minimal (synthesised litellm-shaped
exceptions and responses); they are NOT a full LiteLLM mock layer.

## Per-provider FR-to-test traceability

The provider-compatibility audit does not have its own FR/SR
markers — it is a cross-cutting concern. Coverage is captured in
`docs/traceability/fr-to-test.md` under the relevant per-spec
sections (003 turn-loop, 005 summarizer, 006 MCP server). This
document is the authoritative cross-reference for those tables.

---

## Phase 3 follow-up triggers

- **Streaming dispatch**: when latency-budget pressure forces moving
  off `acompletion` to `acompletion(stream=True)`. Activates the
  per-provider stream-framing column.
- **Self-host cost attribution**: when a deployment runs
  GPU-self-hosted Ollama and operators need to attribute compute
  cost. Adds participant-level cost overrides.
- **Deprecation normalisation**: when LiteLLM ships a provider-
  deprecation event shape. Adds the security_events row and operator
  notification surface.
- **Tool-use / function-calling**: when an orchestrator-internal helper
  function (search, calculator, code-eval) is needed. Adds the per-
  provider tool-use column to a real test matrix.
