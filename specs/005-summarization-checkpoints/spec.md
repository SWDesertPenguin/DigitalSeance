# Feature Specification: Summarization Checkpoints

**Feature Branch**: `005-summarization-checkpoints`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "Summarization checkpoints — structured JSON summaries every N turns capturing decisions, open questions, key positions, and narrative for context assembly"

## Clarifications

### Session 2026-04-14

- Q: Non-blocking semantics? → A: Async task (asyncio.create_task fire-and-forget; loop proceeds immediately; summary lands whenever it finishes)
- Q: Cheapest-model selection when Ollama is present? → A: Prefer lowest cost among paid participants; fall back to free models only if no paid models exist (avoids always picking slow local)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Checkpoint Trigger (Priority: P1)

The orchestrator monitors the turn count since the last summarization checkpoint. When a configurable threshold is reached (default 50 turns), it triggers a summarization pass. The trigger is evaluated after each turn as part of the loop, but does not block the next turn — summarization can run asynchronously.

**Why this priority**: Without a trigger, checkpoints never fire. This is the activation mechanism.

**Independent Test**: Can be tested by advancing the turn counter past the threshold and verifying the trigger fires, then verifying it does not fire again until the next threshold.

**Acceptance Scenarios**:

1. **Given** a session at turn 49 with last_summary_turn = 0 and threshold = 50, **When** turn 50 completes, **Then** a summarization is triggered.
2. **Given** a summarization was just completed, **When** the next turn completes, **Then** no summarization is triggered until the threshold is reached again.
3. **Given** a configurable threshold, **When** the session is configured for 30-turn checkpoints, **Then** summarization fires every 30 turns.

---

### User Story 2 - Structured Summary Generation (Priority: P1)

When summarization is triggered, the system sends the accumulated turns (since the last checkpoint) to the cheapest available AI model with a prompt requesting structured JSON output. The expected output contains four sections: decisions made, open questions, key positions per participant, and a narrative overview.

**Why this priority**: The summary content is what gets used by context assembly. Without structured output, the summary is less useful for building coherent context.

**Independent Test**: Can be tested by providing a block of conversation turns and verifying the summarization prompt is sent to a cheap model and the response is parsed into the expected JSON structure.

**Acceptance Scenarios**:

1. **Given** accumulated turns since the last checkpoint, **When** summarization runs, **Then** the turns are sent to the cheapest available model with a structured summarization prompt.
2. **Given** a valid JSON summary response, **When** it is parsed, **Then** it contains decisions, open_questions, key_positions, and narrative sections.
3. **Given** an invalid JSON response from the model, **When** parsing fails, **Then** the system retries up to 3 times before falling back to storing the raw response as narrative-only.
4. **Given** a successful summary, **When** it is stored, **Then** it is persisted as a message with speaker_type='summary' and the session's last_summary_turn is updated.

---

### User Story 3 - Summary Storage and Retrieval (Priority: P1)

Completed summaries are stored as immutable messages in the transcript with speaker_type='summary'. The content field contains the structured JSON. The session's last_summary_turn field is updated to mark the checkpoint. Context assembly (feature 003) already reads summaries — this story ensures they are stored in the correct format.

**Why this priority**: Storage in the correct format is required for context assembly to parse and use the summaries.

**Independent Test**: Can be tested by generating a summary, storing it, and verifying it can be retrieved via the existing get_summaries method with correct JSON content.

**Acceptance Scenarios**:

1. **Given** a completed summary, **When** it is stored, **Then** a message is created with speaker_type='summary', speaker_id='system', and content containing valid JSON.
2. **Given** a stored summary, **When** retrieved via get_summaries, **Then** the JSON can be parsed into decisions, open_questions, key_positions, and narrative.
3. **Given** a stored summary, **When** the session is queried, **Then** last_summary_turn reflects the turn number of the latest checkpoint.

---

### User Story 4 - Cross-Model Checkpoint Compatibility (Priority: P2)

The summarization prompt must work across different model families (Claude, GPT, Llama, Mistral). The system uses the cheapest available model for cost efficiency but falls back to other models if the cheap model fails. The prompt is designed to produce valid JSON from models with varying JSON capabilities.

**Why this priority**: SACP is multi-model by design. Summaries that only work with one provider defeat the purpose.

**Independent Test**: Can be tested by sending the summarization prompt to mock providers simulating different model families and verifying JSON output is parsed correctly or fallback activates.

**Acceptance Scenarios**:

1. **Given** multiple active participants with different providers, **When** summarization runs, **Then** the cheapest model is selected regardless of provider.
2. **Given** the cheapest model fails to produce valid JSON after 3 retries, **When** fallback activates, **Then** the next cheapest model is tried.
3. **Given** all models fail to produce valid JSON, **When** all retries are exhausted, **Then** the raw response is stored as narrative-only with a warning logged.

---

### User Story 5 - Summary Preservation Across Deletion (Priority: P3)

Summaries are regular messages (speaker_type='summary') and follow the same immutability and lifecycle rules as all other messages. They are deleted only when the session is deleted (atomic deletion from feature 001). They are never individually deletable or editable.

**Why this priority**: This is an integrity guarantee that comes naturally from the existing data model, but it's worth validating explicitly.

**Independent Test**: Can be tested by creating a summary, then verifying it cannot be modified and survives session operations (pause, archive) but is removed on session deletion.

**Acceptance Scenarios**:

1. **Given** a stored summary, **When** an attempt is made to modify it, **Then** the modification is rejected (immutable messages).
2. **Given** a session with summaries, **When** the session is archived, **Then** summaries remain accessible.
3. **Given** a session with summaries, **When** the session is deleted, **Then** summaries are removed as part of atomic deletion.

---

### Edge Cases

- What happens when there are fewer turns than the threshold at session start? No summarization fires until the threshold is reached.
- What happens when the cheapest model has a very small context window? The summarization input is truncated to fit, prioritizing the most recent turns.
- What happens when summarization produces a summary that's too large for context assembly? The summary is stored as-is but context assembly may truncate it based on token budget.
- What happens when two summarizations trigger simultaneously (race condition)? The trigger uses the session's last_summary_turn as a guard — only one fires.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST trigger summarization when (current_turn - last_summary_turn) reaches a configurable threshold (default 50).
- **FR-002**: System MUST send accumulated turns to the cheapest available AI model for summarization.
- **FR-003**: System MUST request structured JSON output with four sections: decisions, open_questions, key_positions, narrative.
- **FR-004**: System MUST retry up to 3 times on invalid JSON responses before falling back to narrative-only storage.
- **FR-005**: System MUST store summaries as messages with speaker_type='summary' and speaker_id='system'.
- **FR-006**: System MUST update session.last_summary_turn after each successful checkpoint.
- **FR-007**: System MUST select the cheapest model by comparing cost_per_input_token across active participants. Selection order: (1) lowest cost_per_input_token where cost > 0; (2) only if no paid models exist, fall back to free/null-cost participants (e.g., Ollama). This prevents summarization from always routing to slow local models.
- **FR-008**: System MUST fall back to the next cheapest model if the primary fails after retries.
- **FR-009**: System MUST log a warning when falling back to narrative-only storage.
- **FR-010**: System MUST not block the turn loop during summarization. Summarization MUST run as an `asyncio.create_task` fire-and-forget coroutine — the loop advances to the next turn immediately without waiting for the summary to complete.

### Key Entities

- **Summarization Checkpoint**: A structured JSON message stored as speaker_type='summary'. Contains decisions (with turn references and status), open questions, per-participant key positions, and a narrative overview.
- **Summary Trigger**: Logic that evaluates whether the turn count threshold has been reached since the last checkpoint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Summarization fires within 1 turn of the threshold being reached.
- **SC-002**: 90%+ of summarization attempts produce valid structured JSON on the first try (well-designed prompt).
- **SC-003**: Summaries are retrievable via get_summaries and parseable into the expected 4-section structure.
- **SC-004**: The turn loop is never blocked by summarization — it completes within the same turn cycle or runs asynchronously.
- **SC-005**: Cheapest model selection correctly identifies the lowest-cost participant across providers.

## Assumptions

- The summarization prompt is a constant string in Phase 1. Prompt optimization is a future iteration.
- "Cheapest model" is determined by cost_per_input_token from the participants table. Paid participants (cost > 0) are preferred over free/null-cost participants; only if no paid models are available does selection fall back to free models (avoiding slow local models for a hot-path operation like summarization).
- Summarization runs using the existing ProviderBridge from feature 003. No new provider integration needed.
- The summary JSON schema is: `{"decisions": [...], "open_questions": [...], "key_positions": [...], "narrative": "..."}`. Schema validation is lenient — missing fields default to empty arrays/strings.
- Summary epoch tracking (message.summary_epoch field) groups messages under their checkpoint. The epoch increments with each checkpoint.
- Context assembly (feature 003) already reads summaries via MessageRepository.get_summaries. This feature ensures summaries are written in the format context assembly expects.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). Summarization is triggered and executed by the orchestrator after turn N. Topology 7 (client-side AI) has no central summarizer; peer summary coordination is deferred to Phase 2+.

**Use cases** (per constitution §1): Serves all use cases that involve long sessions or knowledge-intensive collaboration — research co-authorship, consulting, and technical audits — where token budgets necessitate periodic compression without losing continuity.
