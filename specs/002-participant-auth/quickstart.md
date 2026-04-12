# Quickstart: Participant Auth Development

**Feature**: 002-participant-auth

## Prerequisites

- Feature 001 (core data model) merged to main
- PostgreSQL 16 running via `docker compose up -d postgres`
- `alembic upgrade head` applied (001 schema)

## Setup

```bash
# Ensure on the feature branch
git checkout 002-participant-auth

# Apply new migration (adds token_expires_at + bound_ip)
alembic upgrade head

# Verify new columns
docker compose exec postgres psql -U sacp -d sacp \
  -c "SELECT column_name FROM information_schema.columns WHERE table_name='participants' AND column_name IN ('token_expires_at', 'bound_ip')"
```

## Running Tests

```bash
# All auth tests
pytest tests/test_auth_service.py tests/test_approval.py tests/test_facilitator.py tests/test_ip_binding.py tests/test_token_expiry.py

# Specific story
pytest tests/test_auth_service.py     # US1: Token validation
pytest tests/test_approval.py         # US2: Approval flow
pytest tests/test_facilitator.py      # US6: Transfer
pytest tests/test_ip_binding.py       # US8: Session binding
pytest tests/test_token_expiry.py     # US7: Expiry
```

## Key Environment Variables

Same as feature 001. No new env vars required.
Token expiry period is a constant in the auth service (default 30 days).
