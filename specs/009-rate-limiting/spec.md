# Feature Specification: Rate Limiting

**Feature Branch**: `009-rate-limiting`
**Created**: 2026-04-12
**Status**: Draft

## Clarifications

### Session 2026-04-14

- Q: Which window algorithm? → A: Sliding window (track individual request timestamps, prune old ones)
- Q: Counter persistence? → A: In-memory only (resets on process restart)
- Q: Configuration source? → A: Fixed process-level default (60 req/min hardcoded, no override in Phase 1)
- Q: Scope of enforcement? → A: All authenticated /tools/* endpoints uniformly (reads and writes count equally)
- Q: Retry-After semantics? → A: Seconds until oldest in-window request expires (precise, computed per participant)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-Participant Rate Limiting (Priority: P1)

Each participant shares a process-level rate limit on tool calls (60 requests per minute in Phase 1 — not per-participant configurable). When the limit is exceeded, subsequent requests are rejected with a 429 status until the window resets. Rate limits are tracked per participant, not globally.

**Acceptance Scenarios**:

1. **Given** a participant within their rate limit, **When** they make a tool call, **Then** it succeeds normally.
2. **Given** a participant who has exceeded their limit, **When** they make another call, **Then** it is rejected with a 429 Too Many Requests response.
3. **Given** a rate-limited participant, **When** the time window resets, **Then** they can make calls again.
4. **Given** two participants, **When** one hits their limit, **Then** the other is unaffected.

## Requirements *(mandatory)*

- **FR-001**: System MUST track request counts per participant using a sliding window algorithm (individual timestamps pruned as they fall outside the window).
- **FR-002**: System MUST reject requests exceeding the limit with HTTP 429.
- **FR-003**: System MUST include a Retry-After header in 429 responses. The value MUST be the number of seconds until the oldest timestamp in the sliding window expires (not the full window length).
- **FR-004**: Rate limits MUST be per-participant, never global or pooled.
- **FR-005**: Counters MAY be in-memory only — persistence across process restarts is not required for Phase 1.
- **FR-006**: Rate limiting MUST apply to all authenticated `/tools/*` endpoints uniformly; reads and writes count equally toward the per-participant limit.

## Success Criteria

- **SC-001**: Requests within limit succeed; requests over limit return 429.
- **SC-002**: Rate limit resets after the configured window.
