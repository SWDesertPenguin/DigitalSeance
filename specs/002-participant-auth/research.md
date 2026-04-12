# Phase 0: Research — Participant Auth & Lifecycle

**Feature**: 002-participant-auth
**Date**: 2026-04-11

## Research Tasks

### R1: Auth Service Pattern

**Decision**: Thin AuthService class that composes existing repositories. Not a new repository — an orchestration layer that calls ParticipantRepository and LogRepository.

**Rationale**: Auth operations span multiple repositories (validate token in participants, log to admin_audit_log, update session facilitator_id). A service class coordinates these without adding database access code. Keeps repositories focused on single-table operations.

### R2: Token Validation Performance

**Decision**: bcrypt.checkpw is the bottleneck (~200ms at cost factor 12). Acceptable for Phase 1 with 2 participants. No caching of validated tokens in Phase 1.

**Rationale**: Caching validated tokens would bypass expiry checks and create invalidation complexity. At 2 participants, the 200ms bcrypt cost is negligible. Phase 3 OAuth eliminates this concern entirely.

### R3: IP Binding Storage

**Decision**: Add `bound_ip` TEXT column to participants table via migration. Set on first successful authentication, cleared on token rotation.

**Rationale**: Simple column addition avoids a separate binding table. IP stored as text (supports both IPv4 and IPv6). Cleared on rotation to allow IP changes when tokens are refreshed.

### R4: Schema Migration Strategy

**Decision**: Single migration (002) adding `token_expires_at` TIMESTAMP and `bound_ip` TEXT to participants table. Both nullable (backward compatible).

**Rationale**: Nullable columns don't break existing code. Existing participants get NULL (no expiry, no binding) until their tokens are rotated.

### R5: Authorization Guard Pattern

**Decision**: Simple guard functions that raise typed errors. Called at the top of service methods, not as decorators or middleware.

**Rationale**: Explicit guard calls at function entry are easier to test, trace, and understand under the 25-line limit. Decorators add hidden complexity. Middleware is MCP-layer concern (feature 003+).

## Resolved Unknowns

All Technical Context fields resolved from existing feature 001 infrastructure.
