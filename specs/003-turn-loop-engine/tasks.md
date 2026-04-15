# Tasks: Turn Loop Engine

**Input**: Design documents from `/specs/003-turn-loop-engine/`
**Prerequisites**: plan.md, spec.md, research.md, contracts/orchestrator.md

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root

---

## Phase 1: Setup

**Purpose**: Dependencies, module scaffolding, error types

- [X] T001 Add `litellm>=1.83.0` to pyproject.toml dependencies and run `uv sync`
- [X] T002 Create `src/orchestrator/` and `src/api_bridge/` directories with `__init__.py`
- [X] T003 [P] Add error types to `src/repositories/errors.py` — AllParticipantsExhaustedError, ProviderDispatchError, ResponseQualityError, BudgetExceededError
- [X] T004 [P] Create data types in `src/orchestrator/types.py` — TurnResult, RoutingDecision, ContextMessage frozen dataclasses

---

## Phase 2: Foundational

**Purpose**: Provider bridge and context assembler — everything depends on these

- [X] T005 Implement `src/api_bridge/format.py` — MessageFormatter: translate ContextMessage list to provider-specific messages array (system/user/assistant roles, boundary markers)
- [X] T006 Implement `src/api_bridge/provider.py` — ProviderBridge: dispatch (decrypt key, call litellm.acompletion, accumulate streaming, extract response, compute cost, discard key) and dispatch_with_retry (exponential backoff on rate limits)
- [X] T007 Implement `src/orchestrator/context.py` — ContextAssembler: assemble (5-priority builder with token budget), estimate_tokens (litellm.token_counter wrapper)
- [X] T008 Create `tests/conftest.py` additions — mock provider fixture (configurable responses: success, empty, timeout, rate limit), session+participants fixture for orchestrator tests

**Checkpoint**: Can assemble context and dispatch to a mock provider

---

## Phase 3: User Story 1 — Single Turn Execution (Priority: P1) MVP

**Goal**: Execute one complete turn end-to-end

- [X] T009 [US1] Implement `src/orchestrator/loop.py` — ConversationLoop with execute_turn method: select speaker → assemble context → dispatch → persist message → log routing + usage
- [X] T010 [US1] Write `tests/test_turn_loop.py` — test single turn persists message with correct speaker/tokens/cost; test routing log records decision; test usage log records cost; test timeout skips turn without halting

**Checkpoint**: One turn executes end-to-end

---

## Phase 4: User Story 2 — Context Assembly (Priority: P1)

**Goal**: 5-priority context with token budget

- [X] T011 [US2] Write `tests/test_context_assembly.py` — test priority order (interjections first, then proposals, then MVC, then summary, then history); test budget not exceeded; test truncation at turn boundaries; test MVC-too-large detection

**Checkpoint**: Context assembly verified with all priority levels

---

## Phase 5: User Story 3 — Provider Dispatch (Priority: P1)

**Goal**: LiteLLM dispatch with streaming, retry, key handling

- [X] T012 [US3] Write `tests/test_provider.py` — test dispatch returns response with tokens/cost; test API key discarded after call; test streaming accumulation; test rate limit retry with backoff; test timeout handling

**Checkpoint**: Provider dispatch handles all response types

---

## Phase 6: User Story 4 — Turn Routing (Priority: P2)

**Goal**: All 8 routing modes

- [X] T013 [US4] Implement `src/orchestrator/router.py` — TurnRouter: next_speaker (round-robin, skip paused/over-budget), route (8-mode evaluation returning RoutingDecision)
- [X] T014 [US4] Write `tests/test_router.py` — one test per mode: always proceeds, review_gate stages, delegate_low reroutes on low complexity, domain_gated filters, burst accumulates then fires, observer checks on interval, addressed_only checks name mention, human_only checks interjection; test routing decision logged correctly

**Checkpoint**: All 8 modes produce correct routing actions

---

## Phase 7: User Story 5+6 — Interrupts + Budget (Priority: P2)

**Goal**: Human interjections take priority; budget ceilings enforced

- [X] T015 [US5] Extend `src/orchestrator/loop.py` — add interrupt processing at top of execute_turn: fetch pending → deliver → mark delivered → include in context
- [X] T015a [US5] (2026-04-15) Move transcript persistence of human interjections from `loop.py:_persist_interjections` to `mcp_server/tools/participant.py:inject_message` so `turn_number` reflects arrival time; add advisory lock in `MessageRepository.append_message` to serialize concurrent inject + AI-turn writes; loop now only uses the interrupt queue for routing/cadence signals
- [X] T016 [US6] Implement `src/orchestrator/budget.py` — BudgetEnforcer: check_budget (query usage_log, compare against ceiling, return bool), uses existing LogRepository.get_participant_cost
- [X] T017 [US6] Write `tests/test_budget.py` — test within-budget proceeds; test exceeded-budget skips; test skip logged with reason; test human can still inject when AI budget exceeded; test budgets never pooled across participants

**Checkpoint**: Interrupts delivered before AI turns; budget ceiling enforced

---

## Phase 8: User Story 7+8 — Circuit Breaker + Error Detection (Priority: P3)

**Goal**: Resilience layer

- [X] T018 [US7] Implement `src/orchestrator/circuit_breaker.py` — CircuitBreaker: record_failure, record_success, is_open; tracks consecutive_timeouts per participant, auto-pauses at threshold
- [X] T019 [US7] Write `tests/test_circuit_breaker.py` — test 3 failures → auto-pause; test success resets counter; test paused participant skipped by router; test remaining participants continue
- [X] T020 [US8] Extend `src/api_bridge/provider.py` — add response quality checks (empty, duplicate, repetitive) in dispatch; retry up to 3x on quality failure

**Checkpoint**: Circuit breaker and error detection operational

---

## Phase 9: User Story 9+10 — Classifier + Review Gate (Priority: P3)

**Goal**: Complexity classification and review gate staging

- [X] T021 [US9] Implement `src/orchestrator/classifier.py` — ComplexityClassifier: classify (pattern-matching heuristic returning ComplexityScore, checks for keywords/patterns indicating low vs high)
- [X] T022 [US9] Write `tests/test_classifier.py` — test confirmations/agreements → low; test proposals/tradeoffs → high; test adversarial content → high; test classification included in routing log
- [X] T023 [US10] Extend `src/orchestrator/loop.py` — add review gate check: if routing decision is 'review_gated', create draft via ReviewGateRepository instead of appending message

**Checkpoint**: Classifier feeds routing; review gate stages responses

---

## Phase 10: Polish

**Purpose**: Module exports, integration, full suite

- [X] T024 [P] Update `src/orchestrator/__init__.py` — export ConversationLoop, ContextAssembler, TurnRouter, ComplexityClassifier, BudgetEnforcer, CircuitBreaker
- [X] T025 [P] Update `src/api_bridge/__init__.py` — export ProviderBridge, MessageFormatter
- [X] T026 Run full test suite (features 001 + 002 + 003) and verify no regressions

---

## Dependencies & Execution Order

- **Setup (1)**: No dependencies
- **Foundational (2)**: Depends on Setup
- **US1 (3)**: Depends on Foundational — first MVP turn
- **US2 (4)**: Depends on Foundational (context assembler built in Phase 2, tested here)
- **US3 (5)**: Depends on Foundational (provider built in Phase 2, tested here)
- **US4 (6)**: Depends on US1 (router needs loop integration)
- **US5+6 (7)**: Depends on US1 (interrupts + budget integrate into loop)
- **US7+8 (8)**: Depends on US3 (circuit breaker wraps provider)
- **US9+10 (9)**: Depends on US4 (classifier feeds router)
- **Polish (10)**: Depends on all

### MVP Scope

**US1 + US2 + US3** (Phases 3-5): One turn executes with proper context and provider dispatch. Proves the engine works.

---

## Notes

- 26 tasks total
- Tests use mock provider — no real API calls
- LiteLLM pinned ≥1.83.0 (constitution §6.3 supply chain requirement)
- 25/5 coding standards enforced — orchestrator functions decomposed into small helpers
