# Quickstart: Turn Loop Engine Development

**Feature**: 003-turn-loop-engine

## Prerequisites

- Features 001 + 002 merged to main
- PostgreSQL 16 running via `docker compose up -d postgres`
- Alembic migrations applied (`alembic upgrade head`)

## Setup

```bash
git checkout 003-turn-loop-engine
uv sync  # installs litellm dependency
```

## Running Tests

```bash
# All turn loop tests
pytest tests/test_turn_loop.py tests/test_context_assembly.py tests/test_router.py tests/test_provider.py tests/test_budget.py tests/test_circuit_breaker.py tests/test_classifier.py

# Specific story
pytest tests/test_turn_loop.py         # US1: turn execution
pytest tests/test_context_assembly.py  # US2: context assembly
pytest tests/test_provider.py          # US3: provider dispatch
pytest tests/test_router.py            # US4: 8 routing modes
pytest tests/test_budget.py            # US6: budget enforcement
pytest tests/test_circuit_breaker.py   # US7: circuit breaker
pytest tests/test_classifier.py        # US9: complexity classifier
```

## Key Notes

- Tests use mock provider (no real API calls)
- LiteLLM pinned ≥1.83.0 (supply chain requirement)
- All tests are async (pytest-asyncio)
