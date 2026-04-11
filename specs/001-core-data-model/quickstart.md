# Quickstart: Core Data Model Development

**Feature**: 001-core-data-model

## Prerequisites

- Python 3.11+
- Docker + Docker Compose (for PostgreSQL 16)
- uv (Python package manager)

## Environment Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd DigitalSeance
git checkout 001-core-data-model

# Create virtual environment
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env

# Generate encryption key (first time only)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste the output into .env as SACP_ENCRYPTION_KEY
```

## Database Setup

```bash
# Start PostgreSQL via Docker Compose
docker compose up -d postgres

# Run migrations
alembic upgrade head

# Verify schema
docker compose exec postgres psql -U sacp -d sacp -c "\dt"
```

## Running Tests

```bash
# Full test suite
pytest

# Specific user story
pytest tests/test_session_crud.py       # US1
pytest tests/test_participant.py        # US2
pytest tests/test_messages.py           # US3
pytest tests/test_logs.py               # US4
pytest tests/test_lifecycle.py          # US5
pytest tests/test_interrupt_queue.py    # US6
pytest tests/test_review_gate.py        # US7
pytest tests/test_invites.py            # US8
pytest tests/test_proposals.py          # US9

# With coverage
pytest --cov=src --cov-report=term-missing
```

## Pre-Commit Hooks

```bash
# Install hooks (first time)
pre-commit install

# Run manually
pre-commit run --all-files
```

Hook chain: gitleaks → trailing whitespace/YAML/TOML → ruff lint+format → bandit SAST → 25/5 standards lint

## Key Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| SACP_ENCRYPTION_KEY | Fernet key for API key encryption | (generated, 44 chars) |
| POSTGRES_HOST | Database host | localhost |
| POSTGRES_PORT | Database port | 5432 |
| POSTGRES_DB | Database name | sacp |
| POSTGRES_USER | Application role | sacp_app |
| POSTGRES_PASSWORD | Application role password | (set in .env) |
| POOL_MIN_SIZE | asyncpg pool minimum | 2 |
| POOL_MAX_SIZE | asyncpg pool maximum | 10 |

## Development Workflow

1. Write/modify code in `src/`
2. Run relevant tests: `pytest tests/test_<story>.py`
3. Run full suite: `pytest`
4. Pre-commit checks: `git commit` (hooks run automatically)
5. If 25/5 violation: refactor function into smaller helpers
