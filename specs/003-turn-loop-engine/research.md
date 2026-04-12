# Phase 0: Research — Turn Loop Engine

**Feature**: 003-turn-loop-engine
**Date**: 2026-04-11

## Research Tasks

### R1: LiteLLM Integration Pattern

**Decision**: Use `litellm.acompletion()` async API with streaming. Single function call handles all providers transparently.

**Rationale**: LiteLLM normalizes 100+ providers behind a single interface. The `acompletion()` function accepts model name, messages array, and API key — returns a standard response object. Streaming via `stream=True` returns an async generator.

### R2: Token Counting

**Decision**: Use `litellm.token_counter(model, text)` for estimation. Accept ~5% variance vs exact tiktoken.

**Rationale**: LiteLLM provides per-model token counting that handles provider differences. Exact tiktoken would require provider-specific logic. 5% variance is acceptable for budget enforcement (err on the side of over-counting).

### R3: Context Assembly Architecture

**Decision**: ContextAssembler class with `assemble(session_id, participant, budget)` method. Returns a list of formatted messages. Does not call provider.

**Rationale**: Separation of assembly from dispatch keeps both testable. Assembler handles priority ordering and token budgeting. Provider bridge handles format translation and network calls.

### R4: Routing as Strategy Pattern

**Decision**: TurnRouter with a route() method that delegates to per-mode handler functions. Each mode is a small function that returns a RoutingDecision dataclass.

**Rationale**: 8 modes need distinct logic but share the same interface. Strategy pattern keeps each mode independently testable. RoutingDecision captures intended/actual/action/reason for logging.

### R5: Mock Provider for Testing

**Decision**: Tests use a mock provider that returns canned responses. No real LiteLLM calls in unit tests. Integration tests (future) call real providers.

**Rationale**: Unit tests must be fast and deterministic. Mock provider returns configurable responses (success, empty, timeout, rate limit) for testing each code path.

## Resolved Unknowns

All Technical Context fields resolved from existing infrastructure + LiteLLM docs.
