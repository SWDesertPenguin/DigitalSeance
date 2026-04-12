# Feature Specification: Convergence Detection & Adaptive Cadence

**Feature Branch**: `004-convergence-cadence`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "Convergence detection with embedding similarity, adaptive cadence pacing, and adversarial rotation for consensus drift prevention"

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
2. **Given** a repetitive conversation (high similarity), **When** cadence is computed, **Then** the delay increases toward the ceiling (maximum: 5 minutes for cruise, 15 seconds for sprint).
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

- What happens when the embedding model fails to load? The convergence detector logs a warning and skips embedding computation — the turn loop continues without convergence detection.
- What happens when there are fewer turns than the sliding window size? The detector uses whatever turns are available and does not flag convergence until the window is full.
- What happens when adversarial rotation targets a paused or over-budget participant? The rotation skips to the next active participant.
- What happens when the cadence delay is longer than a human's patience? Human interjections always reset to floor regardless of computed delay.
- What happens when all participants produce identical responses? Convergence is detected immediately (similarity = 1.0), divergence prompt fires, then escalation if it continues.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compute text embeddings for each AI response asynchronously after the response is persisted.
- **FR-002**: System MUST store embeddings in the convergence log with the similarity score and turn reference.
- **FR-003**: System MUST compute cosine similarity between the current embedding and a configurable sliding window of recent embeddings (default 5 turns).
- **FR-004**: System MUST detect convergence when similarity exceeds a configurable threshold (default 0.85) across the entire sliding window.
- **FR-005**: System MUST inject a divergence prompt into the next turn's context when sustained convergence is detected.
- **FR-006**: System MUST escalate to human review when convergence persists after a divergence prompt.
- **FR-007**: System MUST record convergence events in the convergence log including divergence_prompted and escalated_to_human flags.
- **FR-008**: System MUST adjust turn pacing based on conversation similarity — faster for productive (low similarity), slower for repetitive (high similarity).
- **FR-009**: System MUST respect cadence presets: sprint (2s-15s), cruise (5s-5m), idle (trigger-only).
- **FR-010**: System MUST reset cadence delay to floor on human interjection.
- **FR-011**: System MUST inject an adversarial prompt every N turns (configurable, default 12), rotating across active participants.
- **FR-012**: System MUST log adversarial rotation events in the routing log.
- **FR-013**: System MUST load embedding models exclusively in SafeTensors format — no pickle deserialization.
- **FR-014**: System MUST not block the turn loop during embedding computation.
- **FR-015**: System MUST detect excessive n-gram repetition as a quality signal alongside embedding similarity.
- **FR-016**: Embedding vectors MUST never be exposed through any external interface.

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
