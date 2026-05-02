# Feature Specification: Convergence Detection & Adaptive Cadence

**Feature Branch**: `004-convergence-cadence`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "Convergence detection with embedding similarity, adaptive cadence pacing, and adversarial rotation for consensus drift prevention"

## Clarifications

### Session 2026-04-14

- Q: Cruise cadence ceiling? → A: 60s (reduced from 300s via PR #47; 5-minute freezes unusable in active conversation)
- Q: Minimum window for meaningful convergence? → A: ≥3 prior turns required before computing non-zero similarity (prevents false convergence on turn 2)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Embedding-Based Convergence Detection (Priority: P1)

After each AI turn, the orchestrator computes a text embedding for the response and compares it to a sliding window of recent embeddings. When the conversation is becoming repetitive (high cosine similarity across the window), the system detects convergence and flags it. This happens asynchronously — it does not block the turn loop.

**Why this priority**: Convergence detection is the core capability. Without it, conversations can spiral into repetitive loops with no intervention.

**Independent Test**: Can be tested by computing embeddings for a series of messages, checking similarity scores, and verifying convergence is detected when responses repeat.

**Acceptance Scenarios**:

1. **Given** a new AI response, **When** the embedding is computed, **Then** it is stored in the convergence log with the similarity score against the recent window.
2. **Given** a window of 5 recent embeddings with high similarity (above threshold), **When** convergence is evaluated, **Then** it is flagged as converging.
3. **Given** a window of diverse embeddings with low similarity, **When** convergence is evaluated, **Then** it is not flagged.
4. **Given** embedding computation, **When** it runs, **Then** it does not block the turn loop — it executes asynchronously after the response is persisted.

---

### User Story 2 - Divergence Prompt Injection (Priority: P1)

When sustained convergence is detected (similarity above threshold for the entire sliding window), the system injects a divergence prompt into the next turn's context. The prompt instructs the AI to explore a different angle or challenge the current direction. If convergence persists after the divergence prompt, the system escalates to human review.

**Why this priority**: Detection without action is useless. The divergence prompt is the automated first response to convergence.

**Independent Test**: Can be tested by simulating sustained convergence and verifying the divergence prompt appears in the next context payload and that escalation occurs on continued convergence.

**Acceptance Scenarios**:

1. **Given** sustained convergence across the full window, **When** a divergence prompt is triggered, **Then** it is injected into the next turn's context as a system-level instruction.
2. **Given** a divergence prompt was injected, **When** the next response still shows high convergence, **Then** the system escalates to human review by flagging the session.
3. **Given** a divergence prompt was injected, **When** the next response diverges (low similarity), **Then** no escalation occurs and the convergence flag clears.
4. **Given** a divergence prompt injection, **When** it is logged, **Then** the convergence log records `divergence_prompted = true` for that turn.

---

### User Story 3 - Adaptive Cadence Pacing (Priority: P2)

The turn loop adjusts its pacing based on how productive the conversation is. When responses are diverse and productive (low similarity), the delay between turns decreases (faster conversation). When responses are repetitive (high similarity), the delay increases (slower conversation). Human interjections temporarily drop the delay to minimum for responsive follow-up.

**Why this priority**: Adaptive cadence prevents both wasteful rapid-fire repetition and unnecessarily slow productive conversations. It's a natural extension of convergence measurement.

**Independent Test**: Can be tested by providing similarity scores and verifying the computed delay matches expected values for each cadence preset (sprint, cruise, idle).

**Acceptance Scenarios**:

1. **Given** a productive conversation (low similarity), **When** cadence is computed, **Then** the delay decreases toward the floor (minimum: 5 seconds for cruise, 2 seconds for sprint).
2. **Given** a repetitive conversation (high similarity), **When** cadence is computed, **Then** the delay increases toward the ceiling (maximum: 60 seconds for cruise, 15 seconds for sprint).
3. **Given** a human interjection, **When** cadence is computed, **Then** the delay temporarily drops to the floor for responsive follow-up.
4. **Given** the 'idle' cadence preset, **When** cadence is computed, **Then** no automatic pacing occurs — turns fire only on triggers.

---

### User Story 4 - Adversarial Rotation (Priority: P2)

Every N turns (configurable, default 12), the orchestrator injects a temporary adversarial prompt into the next speaker's context. The prompt instructs them to identify and challenge the weakest assumption in the current direction. The adversarial role rotates across participants so no single AI is permanently contrarian. The injection is logged.

**Why this priority**: Adversarial rotation prevents groupthink in AI-to-AI conversations. Without it, AIs tend to agree and reinforce each other's positions, producing low-value consensus.

**Independent Test**: Can be tested by advancing the turn counter to the adversarial interval and verifying the prompt is injected for the correct participant, then rotates to the next participant on the following interval.

**Acceptance Scenarios**:

1. **Given** the adversarial interval has been reached (e.g., turn 12), **When** the next turn is prepared, **Then** an adversarial prompt is injected into that speaker's context.
2. **Given** a previous adversarial injection for participant A, **When** the next interval is reached, **Then** the adversarial prompt rotates to participant B.
3. **Given** an adversarial prompt injection, **When** it is logged, **Then** the routing log records the action as an adversarial rotation with the participant who received it.
4. **Given** a participant whose AI genuinely cannot find a flaw, **When** they respond to the adversarial prompt, **Then** they can say so explicitly — the system does not force disagreement.

---

### User Story 5 - Nonsense and Quality Detection (Priority: P3)

Beyond embedding similarity, the convergence detector checks for nonsense output: excessive repetition of specific n-grams, responses that are semantically empty, or responses that break conversation framing. These quality signals are combined with embedding similarity for a multi-signal convergence assessment.

**Why this priority**: Embedding similarity alone can miss degenerate outputs (e.g., a response that's technically "different" but nonsensical). Multi-signal detection catches more failure modes.

**Independent Test**: Can be tested by providing known-degenerate responses (repeated phrases, empty content framed as a response) and verifying the quality detector flags them.

**Acceptance Scenarios**:

1. **Given** a response with excessive n-gram repetition, **When** quality is assessed, **Then** it is flagged as low quality.
2. **Given** a semantically empty response (filler text with no substance), **When** quality is assessed alongside the embedding, **Then** the combined score reflects the quality problem.
3. **Given** a high-quality diverse response, **When** quality is assessed, **Then** it passes with no flags.

---

### Edge Cases

- What happens when the embedding model fails to load? The convergence detector logs a warning and skips embedding computation — the turn loop continues without convergence detection. Convergence-related turn behavior (no divergence prompt, no escalation, no cadence adjustment) defaults to "no convergence detected" for the rest of the session.
- What happens when the SafeTensors enforcement (FR-013) rejects a published model that lacks SafeTensors weights? The load fails hard; the detector enters the same warning + skip state as a load failure. Operators MUST republish or pin a model release that includes SafeTensors files.
- What happens during the model's first load if the host has no network access to huggingface.co? The first call to `SentenceTransformer(...)` fetches the model files; without network, the load fails the same as FR-013 enforcement. Air-gapped deployments MUST pre-cache the model in `~/.cache/huggingface/hub/` before startup. Phase 3+ may add an explicit offline-mode flag.
- What happens when there are fewer turns than the sliding window size? The detector uses whatever turns are available and does not flag convergence until the window has at least 3 prior turns (FR-003).
- What happens when adversarial rotation targets a paused or over-budget participant? The rotation skips to the next active participant; the rotation index is NOT advanced for the skipped participant so they get the next adversarial slot when they're active.
- What happens when the cadence delay is longer than a human's patience? Human interjections always reset to floor regardless of computed delay.
- What happens when all participants produce identical responses? Convergence is detected immediately (similarity = 1.0), divergence prompt fires, then escalation if it continues.
- What happens when tier text (or any other context fragment) coincidentally contains a 16-char base32-shaped string? Convergence-detection has no overlap with system-prompt extraction (008 FR-003 canaries), so there is no shared detection surface — the strings are matched against disjoint corpora.
- What happens when the convergence threshold is misconfigured (>1.0 = always converging; <0.0 = never)? Operator error; fail-closed semantics not specified. Phase 3 may add bounds-checking at construction.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compute text embeddings for each AI response asynchronously after the response is persisted.
- **FR-002**: System MUST store embeddings in the convergence log with the similarity score and turn reference.
- **FR-003**: System MUST compute cosine similarity between the current embedding and a configurable sliding window of recent embeddings (default 5 turns). Similarity MUST be reported as 0.0 until the window contains at least 3 prior turns — with fewer turns the signal reflects topicality, not convergence.
- **FR-004**: System MUST detect convergence when similarity exceeds a configurable threshold (default 0.75 — see `DEFAULT_THRESHOLD` in `src/orchestrator/convergence.py`) across the entire sliding window. The threshold is set at `ConvergenceDetector` construction; runtime / env-var override is not exposed in Phase 1 (modify the constant or pass via constructor for tests). Phase 3+ may expose it as `SACP_CONVERGENCE_THRESHOLD`.
- **FR-005**: System MUST inject a divergence prompt into the next turn's context when sustained convergence is detected.
- **FR-006**: System MUST escalate to human review when convergence persists after a divergence prompt.
- **FR-007**: System MUST record convergence events in the convergence log including divergence_prompted and escalated_to_human flags.
- **FR-008**: System MUST adjust turn pacing based on conversation similarity — faster for productive (low similarity), slower for repetitive (high similarity).
- **FR-009**: System MUST respect cadence presets: sprint (2s-15s), cruise (5s-60s), idle (trigger-only).
- **FR-010**: System MUST reset cadence delay to floor on human interjection.
- **FR-011**: System MUST inject an adversarial prompt every N turns (configurable, default 12), rotating across active participants.
- **FR-012**: System MUST log adversarial rotation events in the routing log.
- **FR-013**: System MUST load embedding models exclusively in SafeTensors format — no pickle deserialization. Enforced at `ConvergenceDetector.load_model` by passing `model_kwargs={"use_safetensors": True}` to `SentenceTransformer(...)`, which causes the underlying `transformers.from_pretrained` call to fail hard if the published model lacks SafeTensors weights. Silent fallback to `.bin` (pickle) is the attack surface this requirement closes.
- **FR-014**: System MUST not block the turn loop during embedding computation.
- **FR-015**: System MUST detect excessive n-gram repetition as a quality signal alongside embedding similarity.
- **FR-016**: Embedding vectors MUST never be exposed through any external interface. Enforced at the debug-export layer (`src/mcp_server/tools/debug.py` `_LOG_QUERIES["convergence"]`) by selecting only the `(turn_number, session_id, similarity_score, divergence_prompted, escalated_to_human)` columns from `convergence_log` — the `embedding` BYTEA column is intentionally excluded. New export paths MUST follow this pattern; broad `SELECT *` from `convergence_log` is forbidden in any caller-facing surface.
- **FR-017**: The divergence prompt content (FR-005) and the adversarial prompt content (FR-011) are operator-controlled system text injected into AI context. Their canonical strings live in `src/orchestrator/convergence.py:DIVERGENCE_PROMPT` and `src/orchestrator/adversarial.py:ADVERSARIAL_PROMPT`. Both prompts are EXEMPT from the sanitization pipeline (007 §FR-001) because they are system-trust content, not participant-supplied input. Phase 1 ships both with the same text ("Identify the weakest assumption..."); the prompts are conceptually distinct (FR-005 fires on convergence detection, FR-011 fires on rotation interval) but the wording overlap is accepted residual until adversarial-rotation usage data justifies divergent text.
- **FR-018**: The sliding window (FR-003) operates over `convergence_log` rows only. `convergence_log` rows are written exclusively for AI turns (humans, system messages, and summaries do not produce embeddings), so the window naturally excludes those speaker types. There is no interleaving of human / system content into the window even though the spec wording could be read either way.
- **FR-019**: Async embedding tasks MUST complete before the next turn's routing decision. `process_turn` is awaited synchronously inside the turn loop after persistence (`src/orchestrator/loop.py`); it is NOT fire-and-forget. The "asynchronous" framing in FR-001 means "off the main asyncio coroutine via `run_in_executor`" — the loop awaits the executor result before advancing. This avoids orphan tasks at session shutdown and ordering ambiguity in `convergence_log`.

### Key Entities

- **Convergence Log Entry**: Per-turn record with embedding bytes, similarity score, divergence prompted flag, and escalation flag. Already exists in the data model (feature 001).
- **Cadence State**: In-memory tracking of current delay, last similarity, and preset boundaries per session.
- **Adversarial Counter**: Per-session turn counter tracking turns since last adversarial prompt, with rotation index across participants.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Embedding computation completes within 500ms per turn (MiniLM-L6-v2 is ~80ms on CPU for short texts).
- **SC-002**: Convergence is detected within 1 turn of the window exceeding the similarity threshold.
- **SC-003**: Divergence prompts reduce subsequent similarity by at least 20% in test scenarios.
- **SC-004**: Adaptive cadence adjusts delay within the configured preset range for every turn.
- **SC-005**: Adversarial rotation visits each participant exactly once before cycling.
- **SC-006**: The turn loop is never blocked by embedding computation — convergence runs asynchronously.

## Assumptions

- Embedding model is sentence-transformers all-MiniLM-L6-v2 (~80MB, SafeTensors format only, per constitution §6.7).
- The model is loaded once at orchestrator startup and reused across sessions.
- Convergence detection uses multiple signals (embedding similarity + n-gram repetition) but embedding similarity is the primary signal.
- Adaptive cadence is computed in-memory per session — not persisted to database.
- Adversarial rotation state (counter + rotation index) is in-memory per session — not persisted.
- The convergence log table already exists from feature 001. This feature adds the detection logic.
- The divergence prompt text is a constant — not configurable in Phase 1.
- Escalation to human means flagging the session status, not sending external notifications.

## Threat model traceability

| FR | Defends against | OWASP LLM | NIST AI 100-2 / SP 800-53 |
|----|-----------------|-----------|----------------------------|
| FR-001, FR-002, FR-003, FR-004 (embedding + similarity) | Repetitive-output failure mode (degenerate convergence) | LLM05 | SI-4 |
| FR-005, FR-006, FR-007, FR-017 (divergence prompt + escalation) | Groupthink / undetected drift | LLM05 | SI-4 |
| FR-008, FR-009, FR-010 (cadence pacing) | Throughput abuse / cost runaway | LLM04 | SC-5 |
| FR-011, FR-012 (adversarial rotation) | Multi-agent groupthink | LLM05 | SI-4 |
| FR-013 (SafeTensors-only model load) | Pickle-deserialization supply-chain attack | LLM03 | SR-3, SI-7 |
| FR-014, FR-019 (non-blocking embedding) | Loop starvation / DoS via slow embedding | API4 | SC-5 |
| FR-015 (n-gram repetition) | Degenerate-output false negative | LLM05 | SI-10 |
| FR-016 (embedding never externally exposed) | Embedding-leak via debug/export endpoints | LLM06 | SC-28, SI-15 |
| FR-018 (window scope) | Mis-windowed convergence (humans counted as AI) | — | SI-4 |

Sister cross-references: prompt content (FR-017) is exempt from sanitization (007 §FR-001) because it is system-trust text; convergence_log embedding bytes are stripped at the debug-export layer (010 §FR-4 + this spec FR-016).

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 36 findings; resolution split:

**Code changes**: CHK001 (`SentenceTransformer` load now passes `model_kwargs={"use_safetensors": True}` so the underlying `transformers.from_pretrained` hard-fails on .bin/pickle weights, satisfying the explicit FR-013 mandate that previously rode on sentence-transformers' default behavior).

**Spec amendments (this commit)**: CHK001 (FR-013 codifies the load-time enforcement mechanism), CHK004 (Edge Case for offline / no-network deployments), CHK005 / CHK033 / CHK034 (FR-016 codifies the debug-export filter as the enforcement point + forbids broad `SELECT *`), CHK008 / CHK010 (FR-017 names the canonical prompt strings + accepts shared-text residual + sanitization-exemption rationale), CHK011 (Edge Case clarifies adversarial rotation skip + rotation-index hold), CHK012 (FR-004 default corrected from 0.85 to shipped 0.75 + Phase 3 env-var trigger), CHK013 / CHK018 (FR-018 codifies window-over-AI-turns-only semantics), CHK023 / CHK035 (FR-019 codifies await-not-fire-and-forget — embedding completes before next routing decision), CHK027 / CHK028 (Threat-model traceability table), CHK033 (cross-ref 010 + repository-layer responsibility documented).

**Closed as accepted residual / out-of-scope**: CHK002 (model checksum / signature — accepted; HuggingFace's existing artifact controls are the trust anchor; pin via Phase 3+ if needed), CHK003 (model-load fail-open from a convergence standpoint — accepted: "no convergence detected" is the safer fallback than halting the loop), CHK006 (embedding-storage encryption-at-rest — accepted residual; embedding bytes are not user-supplied content, low leakage value), CHK007 (similarity scores in audit logs — accepted: similarity is operationally important; embedding bytes are stripped per FR-016), CHK009 (sanitization of divergence prompt — FR-017 settles via system-trust exemption), CHK014 (async embedding wording vs awaited reality — FR-019 settles), CHK015 (adversarial interval per-session — implicit single-session counter, no cross-session collision), CHK016 (cadence + rate-limit interaction — math: 60s cruise ceiling = 1 req/min, well under 60 req/min — no constraint), CHK017 (cadence reset interaction with interrupt queue priority — covered by 003 §FR-013), CHK019 / CHK020 ("20% reduction" / "exactly once before cycling" — measurability deferred to integration test suite), CHK021 (model crash mid-session — Edge Case state covers), CHK022 (concurrent embedding ordering — single-await-per-turn enforces order), CHK024 (adversarial input designed to game similarity — accepted residual; mitigation requires LLM-judge layer per 007 FR-003.detect deferred), CHK025 (very-short responses — embeddings still computed; quality detector handles via FR-015), CHK026 (all-paused at adversarial fire — covered by Edge Case), CHK029 (observability — convergence_log + similarity score is the audit; alerting deferred), CHK030 (asyncio embedding budget — accepted residual since FR-019 awaits result), CHK031 (model deprecation trigger — when sentence-transformers >= 4.0 ships, OR when MiniLM-L6-v2 is yanked, OR every 24 months), CHK032 (in-memory state — accepted; restart loosening is briefly observable but bounded), CHK036 (FR-008 vs FR-010 race — interjection always wins per 003 §FR-013).

## Operational notes (Phase F amendment, 2026-05-02)

These items capture operator-facing decisions for convergence detection
and cadence in production. Cross-referenced from
`AUDIT_PLAN.local.md` Batch 5 → 004 ops.

**Model-load failure handling.** `load_model` swallows transformer
exceptions (`Failed to load embedding model — skipping`) and leaves
`_model = None`. `process_turn` short-circuits to `(0.0, False)` when
the model is absent — no convergence detection runs for that session.
Operators should monitor session creation logs for the warning; sustained
failures indicate a missing model cache, network unavailability (during
first-load), or a SafeTensors-lacking model release. Recovery: restore
network access OR pre-cache the model in `~/.cache/huggingface/hub/`,
then restart.

**Embedding-cache disk monitoring.** SentenceTransformer caches model
weights at `~/.cache/huggingface/hub/`. The `all-MiniLM-L6-v2` model
is ~90MB; cache is shared across sessions and grows only when models
are added. Operators should monitor disk usage; the cache rarely
crosses 1GB in Phase 1 single-model deployment.

**Air-gapped deployment workflow.** Pre-cache the model offline:
1. On a host with network: run a one-shot Python that imports
   `SentenceTransformer("all-MiniLM-L6-v2")` to populate the cache.
2. Tar the cache directory.
3. Untar to the production host's `$HOME/.cache/huggingface/hub/`.
4. Set `HF_HUB_OFFLINE=1` in the production env so subsequent loads
   never reach the network.
This is required for any deployment with no outbound HTTPS to
huggingface.co at startup (per Edge Case in spec).

**SafeTensors enforcement at startup.** FR-013 enforces SafeTensors-
only via `model_kwargs={"use_safetensors": True}`. If the published
model lacks SafeTensors weights, the load fails hard — the same path as
network failure. Operators upgrading to a new model release MUST
verify SafeTensors files are present BEFORE rolling out.

**Degraded-mode behaviour.** When the model is unavailable, the session
runs without convergence detection: no divergence prompts fire, no
escalations happen, similarity scores are 0.0. Adaptive cadence still
works (it interpolates over the 0.0 value, yielding floor delays). The
operator visibility surface is the warning log line on load failure.

**Model-update procedure.** Changing the embedding model (e.g.,
`all-MiniLM-L6-v2` → `all-mpnet-base-v2`) invalidates all stored
embeddings — they are model-specific vectors. Procedure: drain or
archive existing sessions, deploy the new model, accept that historical
similarity comparisons across the boundary are meaningless. Phase 3+ may
introduce a `convergence_log.embedding_model_version` column for
explicit segmentation.

**Divergence-prompt content tuning.** Per FR-017 the canonical text
lives in `src/orchestrator/convergence.py:DIVERGENCE_PROMPT` (and the
adversarial-rotation twin in `adversarial.py:ADVERSARIAL_PROMPT`). Both
strings are hardcoded operator-controlled content. Phase 1 ships
identical wording (accepted residual); divergent text is a Phase 3
follow-up gated on operator usage data.

**Adversarial-rotation cadence.** `DEFAULT_INTERVAL=12` turns between
adversarial injections (FR-011). Operators can override per-rotator-
instance via the `interval=` kwarg; there is no env-var override in
Phase 1. Tuning guidance: lower the interval (e.g., 6) for high-
contention conversations where groupthink risk is high; raise it
(e.g., 24) for long, exploratory sessions where the prompt would
become noise.

**Convergence threshold tuning.** `DEFAULT_THRESHOLD=0.75`. Lowering
toward 0.6 increases divergence-prompt false-positive rate (the AIs
get poked even when conversation is genuinely productive); raising
toward 0.85 risks missing slow-drift convergence. Tuning is per-
deployment via the `threshold=` constructor kwarg; Phase 3+ may expose
`SACP_CONVERGENCE_THRESHOLD`.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). Embedding-based convergence detection, adaptive cadence, and adversarial rotation are orchestrator functions executed after each turn. Topology 7 (client-side peer AI) has no orchestrator to compute embeddings or inject divergence prompts; convergence must be detected peer-side in Phase 2+.

**Use cases** (per constitution §1): Primarily serves research co-authorship and open-source coordination (where groupthink is a known risk), and distributed teams (long-running deep dives prone to circular reasoning). Adversarial rotation prevents unanimous consensus in multi-viewpoint scenarios.
