# Implementation Plan: Turn Loop Engine

**Branch**: `003-turn-loop-engine` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-turn-loop-engine/spec.md`

## Summary

Implement the serialized conversation loop that orchestrates SACP sessions: turn execution, context assembly with 5-priority token budget, 8-mode turn routing, LiteLLM provider dispatch with streaming and retry, per-participant budget enforcement, circuit breaker, interrupt queue processing, error detection, pattern-based complexity classification, and review gate integration. Composes existing repositories and auth service.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: asyncpg (existing), litellm>=1.83.0 (NEW)
**Storage**: PostgreSQL 16 (existing)
**Testing**: pytest + pytest-asyncio (existing harness)
**Project Type**: Web service
**Performance Goals**: Turn execution < 90s total (60s provider timeout + 15s grace + overhead)
**Constraints**: 25/5, serialized turns, append-only logs, API keys never logged

## Constitution Check

| Gate | Status | Evidence |
|------|--------|----------|
| **V1 — Sovereignty** | PASS | Per-participant budget, model choice, routing preference |
| **V2 — No cross-phase** | PASS | Round-robin only, pattern classifier, no Phase 2+ features |
| **V3 — Security hierarchy** | PASS | API key decrypted only at dispatch, discarded immediately |
| **V4 — Facilitator bounded** | PASS | Loop operates on session config, no facilitator escalation |
| **V5 — Transparency** | PASS | Every routing decision logged, every turn's cost recorded |
| **V6 — Graceful degradation** | PASS | Timeouts → skip, circuit breaker → pause, never halt |
| **V7 — Coding standards** | PASS | 25/5, type hints, pre-commit |
| **V8 — Data security** | PASS | Keys decrypted at dispatch only, log scrubbing |
| **V9 — Log integrity** | PASS | Routing + usage logs append-only |
| **V10 — AI security** | PARTIAL | Context boundary markers included, full pipeline in feature 004+ |
| **V11 — Supply chain** | PASS | LiteLLM pinned ≥1.83.0 (above compromised versions) |

## Project Structure

### New Files

```text
src/orchestrator/
├── __init__.py
├── loop.py              # ConversationLoop: main async turn execution
├── context.py           # ContextAssembler: 5-priority token budget builder
├── router.py            # TurnRouter: 8-mode routing + round-robin
├── classifier.py        # ComplexityClassifier: pattern-matching heuristic
├── budget.py            # BudgetEnforcer: per-participant cost ceiling
├── circuit_breaker.py   # CircuitBreaker: consecutive failure tracking

src/api_bridge/
├── __init__.py
├── provider.py          # ProviderBridge: LiteLLM dispatch + streaming
├── format.py            # MessageFormatter: provider-specific translation

tests/
├── test_turn_loop.py        # US1: end-to-end turn execution
├── test_context_assembly.py # US2: priority order + budget enforcement
├── test_provider.py         # US3: dispatch + streaming + retry
├── test_router.py           # US4: all 8 routing modes
├── test_budget.py           # US6: budget ceiling enforcement
├── test_circuit_breaker.py  # US7: auto-pause after threshold
├── test_classifier.py       # US9: pattern-matching heuristic
```

### Existing Code to Compose

- `src/repositories/message_repo.py` — append_message, get_recent, get_summaries
- `src/repositories/log_repo.py` — log_routing, log_usage, get_participant_cost
- `src/repositories/interrupt_repo.py` — get_pending, mark_delivered
- `src/repositories/review_gate_repo.py` — create_draft
- `src/repositories/participant_repo.py` — list_participants, get_participant
- `src/repositories/proposal_repo.py` — get_open_proposals
- `src/database/encryption.py` — decrypt_value (API key at dispatch)
- `src/models/types.py` — RoutingPreference, RoutingAction, ComplexityScore

## Complexity Tracking

> V10 partial: context assembly includes `<sacp:ai>` / `<sacp:human>` boundary markers for trust-tier separation, but full AI security pipeline (spotlighting, sanitization, jailbreak detection) is deferred to feature 004+. This is a known Phase 1 limitation, not a violation.
