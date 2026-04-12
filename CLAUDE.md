# great-austin Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-11

## Active Technologies
- Python 3.11+ (constitution §6.1) + asyncpg, bcrypt, cryptography (Fernet) — all already installed (002-participant-auth)
- PostgreSQL 16 via Docker Compose (existing) (002-participant-auth)

- Python 3.11+ (constitution §6.1) + FastAPI, asyncpg, Alembic, cryptography (Fernet), bcrypt (001-core-data-model)

## Project Structure

```text
backend/
frontend/
tests/
```

## Commands

cd src; pytest; ruff check .

## Code Style

Python 3.11+ (constitution §6.1): Follow standard conventions

## Recent Changes
- 002-participant-auth: Added Python 3.11+ (constitution §6.1) + asyncpg, bcrypt, cryptography (Fernet) — all already installed

- 001-core-data-model: Added Python 3.11+ (constitution §6.1) + FastAPI, asyncpg, Alembic, cryptography (Fernet), bcrypt

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
