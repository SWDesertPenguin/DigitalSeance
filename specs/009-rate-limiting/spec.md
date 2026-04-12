# Feature Specification: Rate Limiting

**Feature Branch**: `009-rate-limiting`
**Created**: 2026-04-12
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-Participant Rate Limiting (Priority: P1)

Each participant has a configurable rate limit on tool calls (default: 60 requests per minute). When the limit is exceeded, subsequent requests are rejected with a 429 status until the window resets. Rate limits are tracked per participant, not globally.

**Acceptance Scenarios**:

1. **Given** a participant within their rate limit, **When** they make a tool call, **Then** it succeeds normally.
2. **Given** a participant who has exceeded their limit, **When** they make another call, **Then** it is rejected with a 429 Too Many Requests response.
3. **Given** a rate-limited participant, **When** the time window resets, **Then** they can make calls again.
4. **Given** two participants, **When** one hits their limit, **Then** the other is unaffected.

## Requirements *(mandatory)*

- **FR-001**: System MUST track request counts per participant per time window.
- **FR-002**: System MUST reject requests exceeding the limit with HTTP 429.
- **FR-003**: System MUST include a Retry-After header in 429 responses.
- **FR-004**: Rate limits MUST be per-participant, never global or pooled.

## Success Criteria

- **SC-001**: Requests within limit succeed; requests over limit return 429.
- **SC-002**: Rate limit resets after the configured window.
