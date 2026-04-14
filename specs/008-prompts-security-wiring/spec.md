# Feature Specification: System Prompts & Security Wiring

**Feature Branch**: `008-prompts-security-wiring`
**Created**: 2026-04-12
**Status**: Draft
**Input**: "4-tier delta system prompts and security pipeline integration into turn loop and context assembly"

## Clarifications

### Session 2026-04-14

- Q: Default prompt_tier? → A: `mid` (core rules + collaboration guidelines, ~770 tokens)
- Q: Canary token format? → A: Multi-canary, random rare-string markers at 3 positions (start/mid/end), per-session unique, 16-char base32. No structural format (no HTML comment, no XML tag) so attackers have no pattern to evade.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 4-Tier System Prompt Assembly (Priority: P1)

The system assembles a participant's system prompt from four delta tiers: low (~250 tokens, core rules), mid (~520 tokens, adds collaboration guidelines), high (~480 tokens, adds convergence awareness), max (~480 tokens, adds depth-over-brevity). Each tier builds on the previous. The participant's configured prompt_tier determines which tiers are included.

**Why this priority**: System prompts define how each AI behaves in the conversation. Without tiered prompts, all participants use raw custom prompts with no collaboration framing.

**Acceptance Scenarios**:

1. **Given** a participant with prompt_tier='low', **When** the prompt is assembled, **Then** only the core collaboration rules are included (~250 tokens).
2. **Given** a participant with prompt_tier='max', **When** the prompt is assembled, **Then** all four tiers are included (~1,730 tokens total).
3. **Given** a participant with a custom system_prompt, **When** the prompt is assembled, **Then** the custom prompt is appended after the tier content.

---

### User Story 2 - Security Pipeline in Context Assembly (Priority: P1)

The context assembler applies sanitization and spotlighting when building context. All messages are sanitized (injection patterns stripped). AI messages are additionally spotlighted (datamarked) before inclusion in another participant's context.

**Acceptance Scenarios**:

1. **Given** a message with ChatML tokens, **When** context is assembled, **Then** the tokens are stripped before inclusion.
2. **Given** an AI response being included in another AI's context, **When** context is assembled, **Then** it is datamarked with the source participant's ID.
3. **Given** a human interjection, **When** context is assembled, **Then** it is sanitized but NOT datamarked.

---

### User Story 3 - Security Pipeline in Turn Loop (Priority: P1)

After each AI response is received from the provider, the turn loop runs the output validation pipeline (injection check, exfiltration filter, jailbreak detection). High-risk responses are staged for review instead of entering the transcript.

**Acceptance Scenarios**:

1. **Given** an AI response containing injection markers, **When** output validation runs, **Then** the response is staged for facilitator review.
2. **Given** a clean AI response, **When** output validation runs, **Then** it is persisted normally.
3. **Given** an AI response with markdown image exfiltration, **When** the exfiltration filter runs, **Then** the images are stripped before persistence.

---

### Edge Cases

- What happens when all 4 tiers exceed a small model's context window? The MVC floor check in context assembly catches this — the participant is flagged as too-small for active participation.
- What happens when sanitization strips content that the spotlighting then tries to mark? Sanitization runs first, spotlighting runs on the cleaned content.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST assemble system prompts from configurable tiers (low, mid, high, max) using delta content. Default tier when participant has none set MUST be `mid`.
- **FR-002**: System MUST append participant's custom system_prompt after tier content.
- **FR-003**: System MUST embed **three** canary tokens in each assembled system prompt — one near the start, one in the middle of the tier content, one at the end. Each canary MUST be a 16-character base32 random string (no structural prefix, no HTML comment, no XML tag) so it presents no format pattern for attackers to evade. Canaries MUST be unique per session so detection identifies which session leaked. The prompt extraction detector MUST scan AI output for any of the three canaries.
- **FR-004**: System MUST sanitize all messages during context assembly.
- **FR-005**: System MUST spotlight (datamark) AI messages during context assembly.
- **FR-006**: System MUST run output validation on AI responses before persistence.
- **FR-007**: System MUST run exfiltration filtering on AI responses before persistence.
- **FR-008**: System MUST stage high-risk responses for review instead of persisting.

## Success Criteria *(mandatory)*

- **SC-001**: Tier assembly produces correct token counts for each tier level.
- **SC-002**: Sanitization and spotlighting are applied to every context assembly call.
- **SC-003**: Output validation runs on every AI response before persistence.

## Assumptions

- Tier content is constant text in Phase 1. Dynamic tier content is a future enhancement.
- The tier token budgets are approximate (~250, ~520, ~480, ~480) — exact wording will be refined.
- Canary tokens are high-entropy random strings generated per-session (not derived from the prompt hash), stored in session state so the detector can scan for them on every AI response. Three canaries are placed at start, middle, and end of the prompt to catch selective extraction attacks.
