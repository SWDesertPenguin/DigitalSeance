# Feature Specification: Context Compression and Distillation (Six-Layer Stack)

**Feature Branch**: `026-context-compression`
**Created**: 2026-05-07
**Status**: Draft (multi-phase: Phase 1 layers active or partially landed via fix/* PRs; Phase 2 layer 4 + Phase 3 layers 5+6 scaffold-only)
**Input**: User description: "Phase 2 / Phase 3 context compression and distillation. The architectural decisions are NOT open — they are fixed by the project's compression research bundle and constitutional commitments. Six-layer stack with phase placement (Phase 1: Layers 1+2+3 plus information-density signal, TokenizerAdapter, CompressorService+NoOp; Phase 2: Layer 4 LLMLingua-2 mBERT default; Phase 3: Layer 5 Provence + Layer 6 self-hosted soft/KV-cache methods, both conditional). Per-participant pre-bridge placement is non-negotiable. Cache-vs-compress structural separation is non-negotiable. The convergence detector and adversarial rotation always run on the raw transcript, not on compressed views. Applies to topologies 1-6 (Layers 1-4 orchestrator-driven); Layer 6 applies only to legs running open-weight models the orchestrator controls; Topology 7 uses Layer 1 only via per-MCP-client provider settings. Primary use cases: ALL §1-§7 benefit from caching + structural deduplication; long-running research co-authorship (§2) and technical review and audit (§5) benefit most from Layer 4 hard compression once Phase 2 Web UI enables long-history sessions."

## Overview

The orchestrator's bridge layer dispatches a per-turn context payload
to each participant's provider. As sessions accumulate turns, the
context grows: history, system prompt, tool definitions, custom
prompts. Three pressures result: per-turn dispatch cost grows
linearly with history; mid-context "lost in the middle" effects
degrade reasoning quality; provider-native caching savings are left
on the table when the cached prefix is not stable across turns.

The project's compression research bundle (kept local; do not name
in committed artefacts) settled the architectural shape. This spec
turns those decisions into a constitutional feature — fixing what
ships, what doesn't, where each piece fits, and the security
envelope around all of it.

The compression stack has **six layers**, ordered from cheapest +
most-essential to most-speculative:

1. **Layer 1 — Provider-native prompt caching.** Anthropic
   `cache_control` breakpoints, OpenAI `prompt_cache_key`, Gemini
   `CachedContent`. Zero orchestrator-side compute; the gain is
   provider-side TTFT reduction (Anthropic up to ~85%, OpenAI up
   to ~80%). **Mandatory on every closed-API leg from Phase 1.**
2. **Layer 2 — Structural deduplication of the system prompt.**
   The 4-tier delta-only prompt (spec 008) is structural Layer 2.
   Already shipped; spec 026 documents the integration boundary.
3. **Layer 3 — Rolling-summary checkpoints.** Spec 005 is structural
   Layer 3. Already shipped; spec 026 documents the integration.
4. **Layer 4 — Hard compression of overflow.** LLMLingua-2 mBERT
   (default) and Selective Context (fallback). CPU-feasible;
   ~200ms per 1K tokens; breakeven threshold ~4K tokens for English
   prose. **Phase 2.**
5. **Layer 5 — Retrieval-time compression.** Provence on the
   retrieval path. **Phase 3, gated on retrieval entering the
   design.**
6. **Layer 6 — Self-hosted soft / KV-cache methods.** Activation
   Beacon, ICAE, KV-cache compression on the orchestrator's own
   open-weight model legs (Ollama, vLLM). **Phase 3, gated on
   local-model support landing.**

The information-density signal (spec 004 §FR-020 already shipped via
`fix/quality-density-signal`) is the response-quality counterpart
to compression: it catches high-word-count low-semantic-load output
that would otherwise enter the rolling-summary corpus and degrade
checkpoint quality.

Three architectural commitments are **non-negotiable**:

1. **Per-participant pre-bridge placement.** Compression runs in the
   bridge layer for one participant at a time, on that participant's
   outgoing context window. Shared-transcript compression is
   forbidden — it would violate audit-log integrity (a single
   compression artefact would change every participant's view of
   "what was said") and the facilitator-as-admin governance model
   (compression decisions are operator-side, not negotiated between
   AIs).
2. **Cache-vs-compress structural separation.** Cache the **stable
   prefix** (system prompt + tool defs + history through turn N-1).
   Compress only the **current turn's overflow** when budget
   requires it. The stable prefix MUST NOT be compressed; the
   current turn MUST NOT be cached. Mixing the two destroys the
   prefix-stability the cache depends on AND introduces a
   compressed segment into a cached prefix that future turns will
   re-cache against, locking compression artefacts into the cache
   key.
3. **Convergence detector + adversarial rotation always on raw
   transcript.** Spec 004 reads the message store, not the
   per-participant bridge view. Compression artefacts MUST NOT
   appear in the convergence-window inputs.

The security envelope: **compressed segments are a covert-channel
substrate.** A compromised compressor could embed adversarial
content in the compressed representation that bypasses the spec
007 sanitize / spotlight / output-validate pipeline because the
pipeline did not run on the compressed bytes. Mitigation:
compressed segments inherit the trust tier of their source content
(per spec 007 §7.6 trust-tiered content model) AND structural XML
boundary markers wrap every compressed segment before insertion
into a participant's outgoing window, signalling "this region is
compressed-derived" to any downstream check. The 4-tier prompt
text and tool definitions are **priority tier 1** (cached, never
compressed) — they live in the stable prefix and are immune to
compressor compromise by construction.

This spec is **not a clean scaffold-only spec**. Several Layer 1
and Layer 2/3 deliverables already shipped via fix/* PRs (the
Anthropic cache TTL via `fix/api-bridge-caching`, the tokenizer
adapter via `fix/api-bridge-tokenizer-adapter`, the
density-anomaly signal via `fix/quality-density-signal`). This
spec formalises those landings under a constitutional umbrella
AND scaffolds Phase 2 / Phase 3 layers. Phase 1 implementation
is declared when the audit-fix sequence completes; Phase 2 layer 4
and Phase 3 layers 5+6 stay scaffold-only until their respective
gates open.

## Clarifications

### Architectural decisions are FIXED (not open for revision in this spec)

The following are non-negotiable per the research bundle and
prior fix/* landings; they are NOT clarification candidates:

- Six-layer stack as defined above.
- Phase placement (Phase 1: 1+2+3 + density + interface;
  Phase 2: 4; Phase 3: 5+6 conditional).
- Per-participant pre-bridge placement.
- Cache-vs-compress structural separation.
- Convergence detector reads raw transcript, NOT compressed
  views.
- Compressed segments inherit source trust tier AND get XML
  boundary markers.
- The compressor service interface ships in Phase 1 with a
  NoOpCompressor; Phase 2 adds LLMLingua2mBERTCompressor.

### Empirical defaults requiring calibration

- **Compression breakeven threshold (4000 tokens default).**
  4K is the literature default for LLMLingua-2 mBERT on English
  prose; per-participant tuning on observed Phase 1 traffic may
  raise or lower it. v1 ships 4000 as the
  `SACP_COMPRESSION_THRESHOLD_TOKENS` default; tune in
  `/speckit.clarify` once Phase 1 traffic is available.
- **Information-density threshold (1.5× rolling baseline default).**
  Spec 004's `SACP_DENSITY_ANOMALY_RATIO=1.5` is observational
  (no escalation action in Phase 1). Tune the value once Phase 1
  traffic accumulates for the calibration artefact in
  `tests/calibration/density_distribution.json`.
- **Cache hit rate measurement.** Phase 1 emits cache-hit /
  cache-miss markers to `routing_log`; an external dashboard
  (or spec 016 metrics surface) computes per-session cache
  hit rate. v1 emits the markers; the dashboard wiring is a
  spec 016 follow-up.
- **Phase 2 LLMLingua-2 vs. Selective Context A/B.** Default is
  LLMLingua-2 mBERT; Selective Context is the fallback if
  LLMLingua-2 fails to converge or exceeds the latency budget
  on a given participant's traffic. The A/B is conditional on
  Phase 2 implementation; v1 ships the LLMLingua-2 default and
  leaves the A/B harness for Phase 2 work.
- **Anthropic cache TTL stability.** Anthropic dropped the
  `1h` TTL silently to `5m` default in March 2026. Bridge-layer
  caching config is in a single place
  (`SACP_CACHE_ANTHROPIC_TTL`, default `1h`) so future provider
  changes are a single-env-var update, not a code change.

### Architectural-shape questions (limited scope)

- **`compression_log` table vs. `routing_log` extension.**
  Drafted as: a new `compression_log` table with columns
  (turn_id, participant_id, source_tokens, output_tokens,
  compressor_id, compressor_version, trust_tier, layer,
  created_at). Adding columns to `routing_log` was rejected
  because compression events are a different cardinality
  (per-participant-per-turn vs. routing's per-turn) and the
  per-stage timing pattern of `routing_log` doesn't fit
  multi-row-per-turn compression events. [NEEDS
  CLARIFICATION: confirm dedicated table vs. routing_log
  extension.]
- **NoOpCompressor return shape.** Drafted as: NoOpCompressor
  returns input verbatim with `output_tokens == source_tokens`
  and `layer='noop'`. The `compression_log` row is still
  written so Phase 1 has the per-turn telemetry the Phase 2
  cutover needs. [NEEDS CLARIFICATION: confirm log-on-noop
  vs. only-log-when-real-compression.]
- **Trust-tier inheritance edge cases.** Drafted as: a
  compressed segment's trust tier is the MIN of its source
  segments' trust tiers. Mixed-tier source (a turn that
  combines facilitator-trusted system content with
  participant-supplied content) compresses to the lower tier
  (participant-supplied), and the XML boundary marker
  records the lower tier. [NEEDS CLARIFICATION: confirm
  MIN-tier vs. refuse-to-compress-mixed-tier.]
- **`density_anomaly_flagged` routing_log marker vs. spec
  004's convergence_log row.** Spec 004 already writes a
  convergence_log row with `tier='density_anomaly'` when
  the signal fires. The brief asks for a `routing_log`
  marker too. Drafted as: BOTH writes happen — convergence_log
  carries the signal payload for downstream readers
  (summarizer corpus filtering, etc.); routing_log carries
  the per-turn decision marker for the routing audit trail.
  [NEEDS CLARIFICATION: confirm dual-write vs. routing_log
  alone vs. convergence_log alone.]

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Provider-native caching is configured on every closed-API call with explicit TTL on Anthropic and prompt_cache_key on OpenAI (Priority: P1)

The orchestrator dispatches a turn for a participant on Anthropic.
The bridge layer assembles the cache_control breakpoints on the
stable prefix (system prompt + tool defs + history through turn
N-1) and dispatches with `cache_control={"type":"ephemeral",
"ttl": <SACP_CACHE_ANTHROPIC_TTL>}` on the breakpoint position.
The next turn for the same participant on the same session
hits the cache; Anthropic's response includes the cache-hit
marker; the bridge layer records `routing_log.reason='cache_hit'`
with the cached-prefix-token count. For an OpenAI participant,
the bridge dispatches with `prompt_cache_key=<session_id>` so
all turns within the same session route to the same backend
and share the cached prefix. For a Gemini participant, the
bridge attaches `CachedContent` with the participant's
session-id-derived cache identifier.

**Why this priority**: P1 because Layer 1 is mandatory from
Phase 1 per the research bundle. Without explicit caching
configuration the silent-default change Anthropic made in March
2026 (`1h` → `5m`) would silently degrade every deployment's
cache economics. Explicit config in a single bridge-layer
location is the durable fix.

**Independent Test**: Drive a session with two consecutive turns
for the same Anthropic participant. Inspect the second turn's
dispatched payload — assert `cache_control` is set on the
breakpoint position with the configured TTL. Inspect the
provider response — assert the cache-hit marker is present.
Inspect `routing_log` — assert the second turn carries
`reason='cache_hit'` with the cached-prefix-token count. Repeat
for OpenAI (assert `prompt_cache_key=session_id` in the request)
and Gemini (assert `CachedContent` with the session-id-derived
cache identifier).

**Acceptance Scenarios**:

1. **Given** an Anthropic participant on a session with at least
   2 prior turns, **When** the next turn dispatches, **Then** the
   request payload MUST include `cache_control={"type":"ephemeral",
   "ttl":<SACP_CACHE_ANTHROPIC_TTL>}` at the breakpoint position
   AND the breakpoint position MUST be at the end of the stable
   prefix (history through turn N-1, NOT including the current
   turn).
2. **Given** an OpenAI participant on a session, **When** any
   turn dispatches, **Then** the request payload MUST include
   `prompt_cache_key=<session_id>` AND the value MUST be stable
   across all turns within the same session.
3. **Given** a Gemini participant on a session, **When** any
   turn dispatches, **Then** the request payload MUST attach a
   `CachedContent` reference whose key is derived from
   `session_id`.
4. **Given** the second consecutive turn for any cached-leg
   participant, **When** the provider response includes a
   cache-hit marker, **Then** `routing_log` MUST record
   `reason='cache_hit'` with the cached-prefix-token count.
5. **Given** the first turn for a participant (no prior cache),
   **When** the dispatch fires, **Then** `routing_log` MUST
   record `reason='cache_miss'`.
6. **Given** the bridge layer assembles a request, **When** the
   stable prefix changes between turns (e.g., a tool-list
   refresh per spec 017 invalidates the cached prefix), **Then**
   the bridge MUST emit a cache-miss on the next turn AND the
   `routing_log` MUST record the invalidation reason.

---

### User Story 2 - Information-density signal flags low-content turns and writes to convergence_log (Priority: P1)

A participant's AI produces a long-but-shallow response: many
words, few new ideas. The information-density signal (already
shipped via spec 004 §FR-020) computes the density score against
the rolling baseline; the score exceeds the threshold; a
`convergence_log` row is written with `tier='density_anomaly'`
including the score and the rolling-baseline value. The
information-density signal is observational in Phase 1 (no
escalation action); operators can inspect the
`density_anomaly` rows to identify drift toward content-free
verbosity. The summarizer (spec 005) consumes
`tier='density_anomaly'` rows as input filtering — a
density-flagged turn does NOT enter the summarizer corpus
(future: Phase 2 may strengthen this to "summarizer skips
density-flagged turns by default").

**Why this priority**: P1 because the density signal is the
response-quality counterpart to compression. Without it, the
summarizer corpus accumulates content-free verbosity; the
checkpoint summaries get noisier; downstream context quality
degrades. P1 because the signal is already shipped; this spec
formalises the integration boundary so future amendments don't
break it.

**Independent Test**: Drive a turn whose output is high-word-
count low-semantic-load (synthesised via fixture). Assert the
density score computes above the threshold. Assert a
`convergence_log` row is written with `tier='density_anomaly'`
including the score. Assert `routing_log` records
`reason='density_anomaly_flagged'` for that turn. Drive the
summarizer pipeline; assert the density-flagged turn is filtered
from the summarizer corpus per the spec 005 integration.

**Acceptance Scenarios**:

1. **Given** a turn whose output exceeds the density threshold,
   **When** the signal evaluates, **Then** a `convergence_log`
   row MUST be written with `tier='density_anomaly'`, the score,
   and the rolling baseline.
2. **Given** a density-flagged turn, **When** `routing_log` is
   inspected, **Then** the turn MUST have an entry with
   `reason='density_anomaly_flagged'`.
3. **Given** a density-flagged turn, **When** the summarizer
   pipeline runs, **Then** the turn MUST be filtered from the
   summarizer corpus (filter integration is the new requirement
   beyond spec 004's existing observational signal).
4. **Given** a turn whose output does NOT exceed the threshold,
   **When** the signal evaluates, **Then** no `density_anomaly`
   row MUST be written.
5. **Given** the rolling baseline is uninitialised (first 5
   turns of a session), **When** the signal evaluates, **Then**
   the baseline MUST initialise from those turns AND no
   `density_anomaly` MUST be flagged on the initialisation
   window.

---

### User Story 3 - NoOpCompressor passes content through unchanged; CompressorService interface is in place for Phase 2 wiring (Priority: P1)

The orchestrator's bridge layer instantiates a CompressorService
implementing a stable interface (`compress(payload, target_budget,
trust_tier) -> CompressedSegment`). v1 ships NoOpCompressor as
the default — every call passes input verbatim with
`output_tokens == source_tokens` and `layer='noop'`. A
`compression_log` row is written for every dispatch (even
NoOp) so Phase 1 has the per-turn telemetry the Phase 2 cutover
needs. The interface is the architectural commitment: Phase 2
swaps `SACP_COMPRESSION_DEFAULT_COMPRESSOR=llmlingua2_mbert` to
activate Layer 4 without touching the bridge layer.

**Why this priority**: P1 because the interface is the swap
path. Without the interface in place, Phase 2 wiring is a
high-cost dispatch-path refactor; with it, Phase 2 is "register
a new compressor implementation, flip an env var." Shipping the
interface IS the Phase 1 deliverable; the implementation is a
no-behaviour-change refactor that proves the interface holds.

**Independent Test**: Configure `SACP_COMPRESSION_DEFAULT_COMPRESSOR=noop`.
Drive a turn with a payload above the configured threshold.
Assert NoOpCompressor.compress returns the input verbatim.
Assert the dispatched payload is identical to the un-compressor-
mediated path. Assert `compression_log` has one row with
`compressor_id='noop'`, `output_tokens == source_tokens`,
`layer='noop'`. Verify by an architectural test that no file
under `src/` outside the compressor package imports a concrete
compressor implementation directly — all access goes through
`CompressorService.compress`.

**Acceptance Scenarios**:

1. **Given** the default compressor is `noop`, **When** a turn
   above the threshold dispatches, **Then** the dispatched
   payload MUST be byte-identical to the un-compressor-mediated
   payload.
2. **Given** the default compressor is `noop`, **When** any turn
   dispatches, **Then** a `compression_log` row MUST be written
   with `compressor_id='noop'`, `layer='noop'`, and
   `output_tokens == source_tokens`.
3. **Given** the architectural test scans `src/` for direct
   compressor imports, **When** the test runs, **Then** the
   only matching files MUST be inside the compressor package
   itself.
4. **Given** the CompressorService interface is invoked,
   **When** the call returns, **Then** the response MUST match
   the documented `CompressedSegment` shape: `output_tokens`,
   `output_text`, `trust_tier`, `boundary_marker`, `compressor_id`,
   `compressor_version`.
5. **Given** an unknown compressor name in
   `SACP_COMPRESSION_DEFAULT_COMPRESSOR`, **When** the
   orchestrator starts, **Then** the process MUST exit
   non-zero with an error listing the registered compressor
   names (V16 fail-closed gate).

---

### User Story 4 - LLMLingua2mBERTCompressor engages at threshold; trust-tier markers wrap; cache breakpoint walks (Priority: P2)

Phase 2 is declared. `SACP_COMPRESSION_PHASE2_ENABLED=true`,
`SACP_COMPRESSION_DEFAULT_COMPRESSOR=llmlingua2_mbert`. A
participant's outgoing window for the next turn exceeds the
configured threshold (default 4000 tokens). The bridge layer
calls `LLMLingua2mBERTCompressor.compress(overflow_segment,
target_budget, trust_tier)`. The compressor returns a
compressed segment with the trust tier inherited from source AND
XML boundary markers (`<compressed source-tier="participant"
compressor="llmlingua2_mbert" version="1.0">...</compressed>`).
The bridge inserts the compressed segment into the outgoing
window. The Anthropic cache-control breakpoint walks forward to
absorb the new stable prefix (which now includes the compressed
segment as part of the prefix once it's been used in N+1's
dispatch). `compression_log` records the event.

**Why this priority**: P2 because Phase 2 is the substantive
compression deliverable. Phase 1 (US1+US2+US3) ships the
infrastructure; Phase 2 ships the savings. The trust-tier
wrapping is the security envelope (covert-channel mitigation);
the cache-breakpoint walk is the cache-vs-compress separation
in operational practice.

**Independent Test**: Configure Phase 2 enabled. Drive a turn
whose outgoing window exceeds threshold. Assert
`LLMLingua2mBERTCompressor.compress` is invoked with the
overflow segment, the budget, and the trust tier. Assert the
returned segment carries the inherited trust tier AND the
XML boundary markers. Assert the dispatched payload includes
the compressed segment IN PLACE OF the un-compressed overflow.
Drive the next turn for the same participant; assert the
cache-control breakpoint position has walked forward to include
the now-stable prefix (compressed segment is part of the
cached prefix on N+1's turn).

**Acceptance Scenarios**:

1. **Given** `SACP_COMPRESSION_PHASE2_ENABLED=true` and a turn
   with outgoing window above threshold, **When** the bridge
   assembles the request, **Then** the LLMLingua2mBERTCompressor
   MUST be invoked AND its output MUST replace the overflow
   in the dispatched payload.
2. **Given** a compressed segment is produced, **When** the
   segment is inspected, **Then** it MUST be wrapped in
   `<compressed source-tier="..." compressor="..." version="...">`
   ... `</compressed>` markers.
3. **Given** mixed-tier source, **When** compression runs,
   **Then** the segment's trust tier MUST be the MIN of source
   tiers.
4. **Given** a compressed segment lands at turn N, **When** turn
   N+1 dispatches for the same participant, **Then** the cache-
   control breakpoint MUST walk forward to absorb the now-
   stable prefix (compressed segment included).
5. **Given** a compression event fires, **When**
   `compression_log` is inspected, **Then** one row MUST be
   written with the source_tokens, output_tokens, compressor_id
   (`llmlingua2_mbert`), compressor_version, trust_tier, and
   `layer='hard_compression'`.
6. **Given** the LLMLingua-2 compressor exceeds its latency
   budget on a particular participant's traffic, **When** the
   timeout fires, **Then** the bridge MUST fall back to
   Selective Context AND record both events in
   `compression_log` with sequence ordering preserved.

---

### User Story 5 - Provence integration in retrieval path (Priority: P3)

Phase 3 declares retrieval support (separate spec, not in 026
scope). When that spec lands, spec 026 hosts the Provence
adapter as Layer 5. Provence runs at retrieval time, compressing
retrieved chunks before they're added to the participant's
outgoing window. The integration is gated on retrieval entering
the design — without a retrieval surface there is nothing for
Provence to compress. v1 of spec 026 leaves the Layer 5
interface stub registered with a NoOpProvenceAdapter; the
real adapter lands when retrieval ships.

**Why this priority**: P3 because retrieval is not in any
current Phase 3 spec (013, 014, 015-022 have no retrieval
deliverable). Provence is forward-compat scaffolding only.

**Independent Test**: Verify the Layer 5 adapter slot exists in
the CompressorService registry. Verify `SACP_COMPRESSION_LAYER5_ENABLED`
is unset / false by default. Verify the registry rejects
attempts to engage Layer 5 when no retrieval surface is
configured. Full Provence integration test happens in the
retrieval spec when it lands.

**Acceptance Scenarios**:

1. **Given** Layer 5 is unconfigured, **When** any retrieval-
   adjacent code is invoked, **Then** the NoOpProvenceAdapter
   MUST pass content through unchanged.
2. **Given** the retrieval spec lands, **When** Provence is
   wired, **Then** the integration MUST use the existing
   Layer 5 interface slot (no spec 026 amendment required).

---

### User Story 6 - Layer 6 (self-hosted soft / KV-cache) on Ollama / vLLM legs (Priority: P3)

Phase 3 declares Ollama / vLLM local-model support (per
Constitution §10 Phase 3 list). Spec 026 hosts Layer 6 — soft-
prompt and KV-cache compression methods (Activation Beacon, ICAE)
on legs running open-weight models the orchestrator controls.
**Layer 6 is NEVER applied to closed-API legs** (the closed-API
provider has no surface to accept activation tensors or KV-cache
operations). The Layer 6 interface stub is registered with a
NoOpLayer6Adapter in v1 of spec 026; concrete Activation Beacon
/ ICAE implementations land in the local-model-support spec.

**Why this priority**: P3 because local-model support is not in
any current Phase 3 spec. Layer 6 is forward-compat scaffolding
only.

**Independent Test**: Verify the Layer 6 adapter slot exists.
Verify `SACP_COMPRESSION_LAYER6_ENABLED` is unset / false by
default. Verify any closed-API leg dispatch with Layer 6
attempted is rejected with a clear error.

**Acceptance Scenarios**:

1. **Given** Layer 6 is unconfigured, **When** any dispatch
   fires, **Then** Layer 6 MUST NOT engage.
2. **Given** Layer 6 is configured AND the leg is closed-API
   (Anthropic, OpenAI, Gemini, Groq), **When** dispatch fires,
   **Then** Layer 6 MUST be skipped (the layer is structurally
   inapplicable; not an error).
3. **Given** Layer 6 is configured AND the leg is open-weight
   (Ollama, vLLM, the orchestrator-controlled local backend),
   **When** dispatch fires, **Then** Layer 6 MAY engage per
   the participant's configuration.

---

### Edge Cases

- **Cache key collision across participants on the same
  session.** Each participant's
  `(provider, session_id, participant_id)` tuple keys the cache
  context — never `session_id` alone — so cross-participant
  cache contamination is structurally impossible.
- **Compressed segment cache lifetime exceeds Anthropic TTL.**
  The cache TTL refresh happens on cache hits per Anthropic's
  documented behaviour; sessions with regular traffic keep the
  prefix warm. Sessions with sparse traffic see cache-miss
  on long gaps; this is the same pre-feature behaviour
  documented in `fix/api-bridge-caching`.
- **Compressor raises an exception during compress().** The
  bridge MUST fail closed: log the error, record
  `routing_log.reason='compression_pipeline_error'`, fall
  through to the un-compressed payload. The session continues;
  one bad compression does not gate the loop.
- **Compressed segment exceeds target budget** (compression
  failed to meet the budget). The bridge accepts the
  best-effort output and proceeds. `compression_log` records
  the source / output token counts; operators see the
  efficiency trend and can tune the threshold.
- **Tokenizer mismatch between compressor and target provider.**
  The TokenizerAdapter resolves the participant's target
  tokenizer; the compressor's token count MAY differ from the
  target's. The TokenizerAdapter is consulted post-compression
  to verify the segment fits the target's context window;
  budget-overflow falls back per the existing
  ContextWindowOverflowError path (spec 003 FR-035).
- **Density-flagged turn lands during conclude phase** (spec
  025). The conclude-phase delta still applies; the density
  flag does NOT suppress the conclude turn. The summarizer's
  filter for density-flagged turns means the conclude
  summary may exclude that participant's density-flagged
  conclusion, which is documented behaviour.
- **A compressor changes its output for the same input across
  versions.** The `compressor_version` field on
  `compression_log` lets operators distinguish version-
  migration effects from real drift. Cache breakpoints
  invalidate on compressor version change (the cached prefix
  includes the compressor version as part of the cache key).
- **Layer 6 engaged with a remote-hosted Ollama / vLLM
  instance.** "Self-hosted" here means the orchestrator's
  config controls the model — even if the model is on a
  remote machine, as long as the orchestrator can issue
  activation-tensor or KV-cache operations to it, Layer 6
  applies. Ollama/vLLM endpoints that don't expose those
  operations are functionally closed-API and Layer 6
  is skipped.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Provider-native caching MUST be configured on
  every closed-API leg from Phase 1. Anthropic legs MUST
  attach `cache_control={"type":"ephemeral",
  "ttl":<SACP_CACHE_ANTHROPIC_TTL>}` at the breakpoint
  position. OpenAI legs MUST attach
  `prompt_cache_key=<session_id>`. Gemini legs MUST attach
  `CachedContent` with a session-id-derived cache identifier.
- **FR-002**: Cache-vs-compress structural separation MUST be
  enforced. The stable prefix (system prompt + tool defs +
  history through turn N-1) MUST be cached; the current turn
  MUST NOT be cached. The current turn's overflow MUST be the
  only segment compression operates on; the stable prefix
  MUST NOT be compressed.
- **FR-003**: Cache events MUST be logged to `routing_log`.
  `reason='cache_hit'` on a hit (with cached-prefix-token
  count); `reason='cache_miss'` on a miss; cache-invalidation
  events (e.g., spec 017 tool-list refresh) MUST record the
  invalidation reason in the routing log.
- **FR-004**: A cache key MUST be the tuple
  `(provider, session_id, participant_id, compressor_version)`.
  Cross-participant cache contamination MUST be structurally
  impossible.
- **FR-005**: A `compression_log` table MUST be introduced
  with columns: turn_id, participant_id, source_tokens,
  output_tokens, compressor_id, compressor_version,
  trust_tier, layer, created_at.
- **FR-006**: A `CompressorService` interface MUST be defined
  with at minimum `compress(payload, target_budget, trust_tier)
  -> CompressedSegment` and `register(compressor_id,
  compressor_class)`. Implementations register at module load
  time; the registry is read-only after orchestrator startup.
- **FR-007**: The default compressor in v1 MUST be
  `NoOpCompressor`. NoOpCompressor returns input verbatim with
  `output_tokens == source_tokens` and `layer='noop'`.
  `compression_log` MUST still write a row for NoOp dispatch
  so Phase 1 has the telemetry the Phase 2 cutover needs.
- **FR-008**: A `LLMLingua2mBERTCompressor` MUST be the Phase 2
  default once `SACP_COMPRESSION_PHASE2_ENABLED=true`.
- **FR-009**: A `SelectiveContextCompressor` MUST exist as the
  Phase 2 fallback when LLMLingua2mBERT exceeds latency budget
  on a particular participant's traffic.
- **FR-010**: Compression MUST be per-participant pre-bridge.
  Shared-transcript compression is forbidden. The compressor
  operates on one participant's outgoing window at a time.
- **FR-011**: Compressed segments MUST inherit the trust tier
  of their source (per spec 007 §7.6). Mixed-tier source
  produces a segment with the MIN tier of the inputs.
- **FR-012**: Compressed segments MUST be wrapped in XML
  boundary markers:
  `<compressed source-tier="..." compressor="..." version="...">
  ... </compressed>`. The markers MUST appear in the outgoing
  window before any dispatch.
- **FR-013**: Convergence detector (spec 004) and adversarial
  rotation MUST read the raw transcript via the message store,
  NOT the per-participant bridge view. Compressed segments
  MUST NOT appear in convergence-window inputs.
- **FR-014**: System prompt and tool definitions are priority
  tier 1: cached, NEVER compressed. The compressor MUST refuse
  to operate on tier-1 content.
- **FR-015**: A `TokenizerAdapter` interface MUST exist in the
  bridge layer with three concrete implementations: OpenAI
  tiktoken, Anthropic count_tokens, Google countTokens. Token
  count for budget enforcement MUST come from the target
  provider's adapter.
- **FR-016**: Hard compression MUST trigger when the outgoing
  window's projected token count exceeds
  `SACP_COMPRESSION_THRESHOLD_TOKENS` (default 4000) AS
  measured by the target provider's TokenizerAdapter.
- **FR-017**: The Anthropic cache breakpoint MUST walk forward
  on each turn to include the new stable prefix. After turn N
  produces a compressed segment that becomes part of the
  prefix at turn N+1, the breakpoint position at turn N+1
  MUST include that segment.
- **FR-018**: The information-density signal (already shipped
  via spec 004 §FR-020) MUST be formalised here as Phase 1
  active. The signal writes to `convergence_log` with
  `tier='density_anomaly'` AND emits
  `routing_log.reason='density_anomaly_flagged'`.
- **FR-019**: The summarizer (spec 005) MUST filter
  density-flagged turns from the summarizer corpus. This
  is the new requirement beyond spec 004's existing
  observational signal — Phase 1 wiring strengthens density
  from observational to filter-active for the summarizer
  path only (no other escalation actions in Phase 1).
- **FR-020**: A compression failure MUST fail closed: log the
  error, record `routing_log.reason='compression_pipeline_error'`,
  fall through to the un-compressed payload.
- **FR-021**: Layer 5 (Provence) MUST register a stub adapter
  in v1 (NoOpProvenceAdapter). The real adapter lands in the
  retrieval spec when retrieval enters the design.
- **FR-022**: Layer 6 (Activation Beacon, ICAE, KV-cache) MUST
  register a stub adapter in v1 (NoOpLayer6Adapter). The
  real adapter lands in the local-model-support spec. Layer 6
  MUST be structurally skipped on closed-API legs (no error;
  the layer is inapplicable).
- **FR-023**: An architectural test MUST assert no file under
  `src/` outside the compressor package imports a concrete
  compressor implementation directly. All access MUST go
  through `CompressorService.compress`.
- **FR-024**: An architectural test MUST assert the convergence
  detector code path reads the raw transcript via the
  message-store interface, NOT the per-participant bridge view.
- **FR-025**: The six new env vars (`SACP_CACHE_ANTHROPIC_TTL`,
  `SACP_CACHE_OPENAI_KEY_STRATEGY`,
  `SACP_COMPRESSION_PHASE2_ENABLED`,
  `SACP_COMPRESSION_THRESHOLD_TOKENS`,
  `SACP_COMPRESSION_DEFAULT_COMPRESSOR`,
  `SACP_INFORMATION_DENSITY_THRESHOLD`) MUST have validator
  functions in `src/config/validators.py` registered in the
  `VALIDATORS` tuple, AND corresponding sections in
  `docs/env-vars.md` with the six standard fields, BEFORE
  `/speckit.tasks` is run for this spec (V16 deliverable
  gate).
- **FR-026**: The `sessions.compression_mode` column MUST
  accept `auto` | `off` | `<layer-name>` values. `auto`
  (default) selects layers per the configured defaults;
  `off` disables compression entirely (NoOp regardless of
  threshold); `<layer-name>` forces a specific layer for the
  session.

### Key Entities

- **CompressorService** (process-scope) — registry of
  compressor implementations keyed by id. Read-only after
  startup.
- **NoOpCompressor** — pass-through compressor. Phase 1
  default.
- **LLMLingua2mBERTCompressor** — Phase 2 default. mBERT-based
  filtering compressor.
- **SelectiveContextCompressor** — Phase 2 fallback.
- **TokenizerAdapter** (interface) — token-count abstraction
  with three implementations (OpenAI tiktoken, Anthropic
  count_tokens, Google countTokens).
- **CompressedSegment** — output of `compress()`:
  output_tokens, output_text, trust_tier, boundary_marker,
  compressor_id, compressor_version.
- **compression_log** (table) — per-turn compression event
  records. Append-only per spec 001 §FR-008.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Provider-native caching MUST be configured on
  every closed-API leg. Verified by an integration test
  driving turns through Anthropic, OpenAI, and Gemini and
  asserting the cache-control / prompt_cache_key /
  CachedContent attachments.
- **SC-002**: Cache hit on the second consecutive turn for any
  cached-leg participant MUST record
  `routing_log.reason='cache_hit'` with the cached-prefix-token
  count. Verified by a multi-turn test.
- **SC-003**: Architectural test MUST assert the compressor
  is the only path through which compression-mediated content
  reaches the dispatched payload. CI fails if any new code
  bypasses `CompressorService.compress`.
- **SC-004**: Architectural test MUST assert the convergence
  detector reads the raw transcript, NOT the per-participant
  bridge view. CI fails if any new code bridges raw-transcript
  reads through the compressor.
- **SC-005**: Information-density signal MUST be formalised as
  Phase 1 active and the summarizer MUST filter
  density-flagged turns. Verified by driving a flagged turn
  and asserting the summarizer corpus excludes it.
- **SC-006**: NoOpCompressor MUST produce byte-identical
  output to un-compressor-mediated dispatch. Verified by a
  golden-output regression test with the default compressor.
- **SC-007**: Phase 2 cutover MUST require only an env-var
  change (`SACP_COMPRESSION_DEFAULT_COMPRESSOR=llmlingua2_mbert`),
  NOT a code change. Verified by an integration test that
  flips the env var and asserts the new compressor activates.
- **SC-008**: Compressed segments MUST carry XML boundary
  markers AND the inherited trust tier. Verified by a Phase 2
  integration test asserting the marker contents.
- **SC-009**: Cache key MUST be
  `(provider, session_id, participant_id, compressor_version)`.
  Verified by a cross-participant test asserting no cache
  contamination occurs when two participants on the same
  session use the same provider.
- **SC-010**: Compression failure MUST fail closed with
  un-compressed fallback. Verified by a test driving the
  compressor to raise an exception and asserting the dispatch
  proceeds with the un-compressed payload.
- **SC-011**: Layer 6 MUST be structurally skipped on closed-
  API legs without error. Verified by a test enabling Layer 6
  and dispatching to an Anthropic leg, asserting Layer 6 does
  not engage and no error is raised.
- **SC-012**: With any of the six new env vars set to an
  invalid value, the orchestrator process MUST exit at
  startup with a clear error message naming the offending
  var (V16 fail-closed gate observed in CI).
- **SC-013**: Per-turn compression telemetry MUST be present
  in `compression_log` for every dispatch (including NoOp).
  Verified by a synthetic-load test asserting one
  `compression_log` row per dispatch.

## Topology and Use Case Coverage (V12/V13)

### V12 — Topology Applicability

Per the research bundle's compatibility analysis:

- **Layers 1-4 apply to topologies 1-6** (orchestrator-driven
  pre-bridge placement). The orchestrator owns the per-
  participant context window assembly; compression and
  caching configuration live there.
- **Layer 5 (Provence)** applies to topologies 1-6 IF a
  retrieval surface is configured for those topologies.
  Retrieval is not in any current Phase 3 spec; Layer 5 is
  scaffold-only until that lands.
- **Layer 6 (self-hosted soft / KV-cache)** applies only to
  legs running open-weight models the orchestrator controls
  (Ollama, vLLM). It MUST be skipped on closed-API legs
  regardless of configuration.
- **Topology 7 (MCP-to-MCP, Phase 3+)** uses **Layer 1 only**
  via per-MCP-client provider settings. The orchestrator-
  driven layers (2-6) do not apply because there is no
  orchestrator-side context-assembly hook in topology 7.

### V13 — Use Case Coverage

This feature serves all V13 use cases:

- **All of §1-§7** benefit from Layer 1 caching (provider-
  side TTFT reduction) and Layer 2 structural deduplication
  (already shipped via spec 008).
- **§2 Research Paper Co-authorship** and **§5 Technical
  Review and Audit** benefit most from Layer 4 hard
  compression once Phase 2 Web UI enables long-history
  sessions. Long-running co-authorship sessions accumulate
  context that compression keeps tractable; audit sessions
  with extensive review history benefit from the same
  envelope.
- **§3 Consulting** benefits from Layer 1 caching directly
  (engagement context reuse across the consultant's
  multiple sessions on a deployment via the
  prompt_cache_key strategy).

The information-density signal (FR-018, FR-019) primarily
serves §5 audit (low-content turns are explicit drift signals
in audit reviews) and §2 co-authorship (filtering content-free
exchanges from the summarizer corpus).

## Performance Budgets (V14)

V14 mandates per-stage latency budgets as enforceable
contracts. This spec contributes four budgets:

- **Layer 1 (caching)**: zero orchestrator-side compute. The
  gain is provider-side TTFT reduction (Anthropic up to ~85%,
  OpenAI up to ~80% on second-turn hits per provider
  documentation). Budget enforcement: cache-hit / cache-miss
  markers in `routing_log` plus an external dashboard (or
  spec 016 metrics) for hit-rate measurement.
- **Layer 4 (LLMLingua-2 mBERT)**: ~200ms per 1K tokens on
  CPU. Breakeven threshold for the round-trip cost is ~4K
  tokens for English prose. Budget enforcement: per-call
  timing in `compression_log.duration_ms` (column added to
  the schema).
- **CompressorService dispatch overhead**: O(1) virtual
  method dispatch; the abstraction MUST NOT introduce
  buffering, copying, or serialization beyond what the
  compressor already does. Budget enforcement: per-dispatch
  timing comparison against the un-compressor-mediated
  baseline.
- **Information-density signal**: zero additional cost. The
  signal reuses spec 004's sentence-transformers
  infrastructure (already loaded for convergence). Budget
  enforcement: per-turn `routing_log.shaping_score_ms` (cross-
  ref spec 021 §FR-011) inclusive of density evaluation.

## Configuration (V16) — New Env Vars

Six new env vars are introduced. Each MUST have type, valid
range, and fail-closed semantics documented in
`docs/env-vars.md` BEFORE `/speckit.tasks` is run for this
spec (per V16 deliverable gate).

### `SACP_CACHE_ANTHROPIC_TTL`

- **Intended type**: string with explicit unit suffix
  (e.g., `1h`, `5m`, `30s`)
- **Intended valid range**: `5m` to `24h`. Default `1h`.
  Anthropic dropped the `1h` silent default to `5m` in
  March 2026; explicit configuration here is the durable
  fix.
- **Fail-closed semantics**: any unparseable value MUST
  cause startup exit. Empty values default to `1h`.

### `SACP_CACHE_OPENAI_KEY_STRATEGY`

- **Intended type**: string enum
- **Intended valid range**: `session_id` | `participant_id`.
  Default `session_id`. The session-id strategy keeps a
  session's per-participant fan-out routed to one backend
  for cache hit-rate; participant-id is available for
  operators who explicitly want per-participant cache
  partitioning.
- **Fail-closed semantics**: any non-enum value MUST cause
  startup exit.

### `SACP_COMPRESSION_PHASE2_ENABLED`

- **Intended type**: boolean
- **Intended valid range**: `true` | `false`. Default
  `false` (Phase 2 stays scaffold-only until operators
  opt in).
- **Fail-closed semantics**: any non-parseable value MUST
  cause startup exit.

### `SACP_COMPRESSION_THRESHOLD_TOKENS`

- **Intended type**: positive integer
- **Intended valid range**: `[500, 100000]`. Default
  `4000` (literature default for LLMLingua-2 mBERT on
  English prose).
- **Fail-closed semantics**: outside the range MUST cause
  startup exit. Below 500 makes compression overhead
  dominate any savings; above 100000 effectively disables
  compression for all real workloads.

### `SACP_COMPRESSION_DEFAULT_COMPRESSOR`

- **Intended type**: string from the registered compressor
  registry
- **Intended valid range**: `noop` (Phase 1 default) |
  `llmlingua2_mbert` (Phase 2) | `selective_context`
  (Phase 2 fallback). Default `noop`.
- **Fail-closed semantics**: a value not in the registry
  MUST cause startup exit with an error listing the
  registered compressor names.

### `SACP_INFORMATION_DENSITY_THRESHOLD`

- **Intended type**: positive float
- **Intended valid range**: `(0.0, 10.0)` exclusive. Default
  `1.5` (per spec 004's `SACP_DENSITY_ANOMALY_RATIO`
  default; 1.5× rolling baseline).
- **Fail-closed semantics**: outside the range MUST cause
  startup exit.

## Cross-References to Existing Specs and Design Docs

- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log`
  per-stage timings receive cache-hit / cache-miss /
  compression-applied / density-anomaly-flagged reasons.
  Spec 026 adds these reasons to the routing_log enumeration.
- **Spec 003 (turn-loop-engine) FR-035** — ContextWindowOverflowError
  on per-target-model context budget. The
  TokenizerAdapter (FR-015) feeds the budget calculation;
  compression operates on overflow above
  `SACP_COMPRESSION_THRESHOLD_TOKENS`.
- **Spec 004 (convergence-cadence) §FR-013, §FR-018, §FR-020** —
  convergence detector reads raw transcript (FR-013); reuse of
  sentence-transformers embedding pipeline (FR-018, FR-020)
  for density-anomaly detection. Spec 026 explicitly requires
  raw-transcript reads (FR-013, FR-024).
- **Spec 005 (summarization-checkpoints)** — Layer 3 of the
  stack. Already shipped. Spec 026 adds the density-anomaly
  filter on the summarizer corpus (FR-019).
- **Spec 007 (ai-security-pipeline) §7.6** — trust-tiered
  content model. Compressed segments inherit source trust
  tier (FR-011); XML boundary markers wrap compressed
  segments (FR-012). The 4-tier prompt text is priority
  tier 1 (FR-014, never compressed).
- **Spec 008 (prompts-security-wiring)** — Layer 2 of the
  stack. The 4-tier delta-only prompt is structural
  deduplication. System prompt and tool defs are priority
  tier 1 (FR-014).
- **Spec 011 (web-ui)** — admin panel surfaces compression
  metrics: compression ratio per turn, cache hit rate,
  information-density baseline. Coordinated FR additions to
  011 once 026 reaches Implemented.
- **Spec 016 (prometheus-metrics)** — cache hit rate,
  compression ratio, density-anomaly rate are metric
  candidates. The metric-export wiring lands in spec 016
  follow-ups when 026 stabilises.
- **Spec 017 (tool-list-freshness)** — tool-list refresh
  invalidates the cached prefix. The cache-miss event with
  invalidation-reason logging (FR-003) integrates with 017's
  `prompt_cache_invalidated` field.
- **Spec 020 (provider-adapter-abstraction)** — Layer 1
  caching wires through the adapter (FR-001). The Anthropic
  adapter attaches `cache_control`; the OpenAI adapter
  attaches `prompt_cache_key`; the Gemini adapter attaches
  `CachedContent`. Spec 020's FR-010 cache-control
  normalisation covers this.
- **Spec 001 (core-data-model)** — schema additions:
  `sessions.compression_mode` column, new
  `compression_log` table. Append-only per §FR-008.
  Migration follows §FR-017 forward-only constraint.
- **Spec 015 (provider-failure-detection)** — bridge-layer
  circuit breaker is unaffected by compression; circuit
  state is tracked per participant per provider; compression
  is internal to the bridge.
- **Constitution §10** — Phase 3 deliverables list. Spec 026
  is multi-phase: Phase 1 layers active or partially
  shipped; Phase 2 scaffolded; Phase 3 layers conditional
  on retrieval / local-model-support spec landings.
- **Constitution §14.1** — Feature work workflow.
- **Constitution V12** — topology applicability. Layers 1-4
  apply to topologies 1-6; Layer 6 to open-weight legs
  only; Topology 7 uses Layer 1 alone.
- **Constitution V13** — primary use cases all (§1-§7) benefit
  from Layers 1-2; §2 + §5 benefit most from Layer 4.
- **Constitution V14** — per-stage timing budgets. Spec 026
  contributes four budgets (Performance Budgets section).
- **Constitution V16** — env-var validation at startup.
  Spec 026 introduces six new vars (Configuration section).

## Out of Scope (Hard Do Not Build)

The research bundle settled the following negative
commitments. These items are explicitly OUT OF SCOPE; future
amendments to spec 026 may NOT introduce them without an
explicit research-bundle update AND constitutional review:

- **GPTCache.** Maintenance frozen 2024; provider-native
  caching makes it redundant. Do not add a wrapper.
- **Original LLMLingua (LLaMA-7B compressor).** Heavy
  infrastructure for Phase 1+2 gain; production-latency
  studies showed real-world speedups well below paper
  headlines. LLMLingua-2 mBERT is the direction.
- **KV-cache compression on closed-API legs.** Closed-API
  providers do not expose KV-cache operations.
- **Soft-prompt methods on closed-API legs.** Closed-API
  providers do not accept activation-tensor inputs.
- **Shared-transcript compression.** Violates audit-log
  integrity and facilitator-as-admin governance. Per-
  participant pre-bridge placement is the only correct
  shape (FR-010).
- **Automatic conversation truncation.** Use rolling-
  summary checkpoints (Layer 3, spec 005) instead.
- **Negotiated inter-AI shorthand.** Rejected on cost
  calculus, audit integrity, security threat model, and
  drift problem. The §4.13 default-deny baseline rejects
  this category at all phases.
- **CompAct in default RAG path.** Iterative LLM passes
  hurt TTFT.
- **Cross-participant compression caching.** The cache
  key MUST be participant-scoped (FR-004) to preserve
  sovereignty and prevent cross-participant content
  leakage via cache rehydration.

## Assumptions

- The architectural decisions in this spec are settled by
  the project's compression research bundle and constitutional
  commitments. They are NOT clarification candidates;
  `/speckit.clarify` resolves only the empirical defaults and
  limited architectural-shape questions noted in
  Clarifications.
- Per-participant pre-bridge placement is the only correct
  placement. Any future amendment that proposes shared-
  transcript compression OR cross-participant cache
  rehydration MUST be rejected as drafted.
- Cache-vs-compress structural separation is the operational
  invariant the cache economics depend on. Mixing the two
  destroys the prefix stability the cache exploits.
- The convergence detector and adversarial rotation always
  read the raw transcript via the message-store interface.
  Compression artefacts MUST NOT appear in convergence-
  window inputs (FR-013, FR-024 architectural-test
  enforcement).
- Compressed segments are a covert-channel substrate. The
  trust-tier inheritance + XML boundary marker envelope
  (FR-011, FR-012) is the specific control matching that
  risk surface; weakening either weakens the whole envelope.
- The information-density signal is observational in Phase 1
  (no escalation action) per spec 004; spec 026 adds one
  filter integration (summarizer corpus) on top of the
  observational signal. Stronger escalation actions are
  Phase 2+ candidates.
- The Anthropic cache TTL silent-default change (March 2026)
  is the canonical example of why bridge-layer caching
  config lives in a single place: future provider changes
  are a single env-var update, not a code change.
- The CompressorService interface is the swap path. Phase 2
  cutover is one env-var change; future compressors slot in
  via the registry without dispatch-path changes (FR-006).
- Layer 5 (Provence) and Layer 6 (Activation Beacon, ICAE,
  KV-cache) are forward-compat scaffolds. They land
  behaviourally only when the retrieval and local-model-
  support specs ship.
- TokenizerAdapter resolves provider tokenizer mismatch at
  the bridge layer once. Per-call tokenizer detection in the
  compressor is forbidden — it would re-introduce the
  tokenizer mismatch problem the adapter solves.
- The hard "do not build" list constrains future amendments.
  Any item added to that list moving into scope requires
  an explicit research-bundle update AND constitutional
  review per §14.5.
- Phase 1 implementation is declared when the audit-fix
  sequence completes (per the brief). The spec stays
  multi-phase Draft until then.
- Status remains Draft until the audit-fix sequence
  completes for Phase 1 portions AND the user accepts the
  scaffolding for Phase 2 + Phase 3 portions.
