# Phase 0: Research — Core Data Model

**Feature**: 001-core-data-model
**Date**: 2026-04-11

## Research Tasks

### R1: ORM vs Direct asyncpg

**Decision**: Direct asyncpg with prepared statements — no ORM.

**Rationale**: The design doc (§4.1, §4.2) explicitly specifies asyncpg with connection pooling and prepared statements for hot-path queries. The 25-line function cap (constitution §6.10) naturally limits query complexity, making an ORM's abstraction unnecessary. asyncpg provides ~3x throughput over SQLAlchemy async for simple CRUD operations and gives direct control over prepared statements.

**Alternatives considered**:
- SQLAlchemy 2.0 async — rejected: adds abstraction layer without benefit for a schema this stable. Increases dependency surface. Not mentioned in design doc.
- Tortoise ORM — rejected: less mature async ORM, smaller ecosystem.
- Raw SQL strings — rejected: asyncpg with parameterized queries already provides this with type safety.

### R2: Migration Strategy (Alembic with asyncpg)

**Decision**: Alembic with programmatic runner. Migrations use raw SQL (not ORM autogenerate).

**Rationale**: Constitution §6.2 specifies Alembic. Since we're not using SQLAlchemy ORM, migrations use raw SQL in upgrade/downgrade functions. Programmatic runner (`alembic.command.upgrade`) called at application startup to ensure schema is current. Forward-only in production (constitution assumption: no rollback migrations).

**Alternatives considered**:
- yoyo-migrations — rejected: less ecosystem support, not specified in constitution.
- Manual SQL scripts — rejected: no version tracking, no dependency ordering.

### R3: Dataclass Model Pattern

**Decision**: Frozen dataclasses with `__slots__` for all entity models. Factory classmethods for construction from asyncpg Records.

**Rationale**: Frozen dataclasses enforce immutability at the Python layer (aligns with message/log immutability guarantees). `__slots__` reduces memory overhead. Factory methods (`from_record`) keep construction logic in one place. The coding standards (§ decomposition guidance) recommend frozen dataclass carriers when state threads through 3+ helpers.

**Alternatives considered**:
- Pydantic models — rejected: validation overhead unnecessary for DB-sourced data already validated at insert. Adds dependency.
- TypedDict — rejected: no runtime immutability enforcement, less ergonomic.
- attrs — rejected: similar to dataclasses but adds dependency without clear benefit.

### R4: API Key Encryption (Fernet)

**Decision**: cryptography library's Fernet class. Single symmetric key from environment variable `SACP_ENCRYPTION_KEY`. Key generated via `Fernet.generate_key()` on first deployment.

**Rationale**: Constitution §6.5 specifies Fernet encryption for API keys at rest. The .env.example already includes `SACP_ENCRYPTION_KEY`. Fernet provides authenticated encryption (AES-128-CBC + HMAC-SHA256) — decryption fails loudly on tampering. Phase 2 migrates to envelope encryption (DEK/KEK).

**Alternatives considered**:
- AES-GCM via raw cryptography — rejected: Fernet wraps this with a simpler API and is constitutionally specified.
- HashiCorp Vault — rejected: Phase 4+ consideration. Over-engineered for Phase 1 Docker Compose deployment.

### R5: Auth Token Hashing (bcrypt)

**Decision**: bcrypt via the `bcrypt` Python package. Cost factor 12 (default). Tokens generated as 32-byte secrets via `secrets.token_urlsafe(32)`.

**Rationale**: Constitution §6.5 specifies bcrypt for token hashing. bcrypt is computationally expensive by design (resistant to brute-force). The token is shown once at creation, then only the hash is stored.

**Alternatives considered**:
- Argon2 — rejected: better algorithm but not constitutionally specified. Would require constitution amendment.
- SHA-256 with salt — rejected: too fast, vulnerable to brute-force.

### R6: Testing Strategy

**Decision**: pytest + pytest-asyncio. Test database created per session (fixture). Each test runs in a transaction that rolls back (fast, isolated).

**Rationale**: pytest is the standard Python test framework. pytest-asyncio handles async test functions. Transaction rollback gives each test a clean slate without the cost of dropping/recreating the database.

**Alternatives considered**:
- unittest — rejected: less ergonomic for async, no fixture composability.
- testcontainers-python — considered for CI: spins up PostgreSQL in Docker per test run. Good complement but not a replacement for local dev.

### R7: Connection Pool Configuration

**Decision**: asyncpg pool with min_size=2, max_size=10 (Phase 1 default). Configurable via environment variables.

**Rationale**: Design doc §4.2 specifies default pool of 10 connections for Phase 1 (2 participants). min_size=2 keeps connections warm for the common case. Statement and idle transaction timeouts configured per constitution §6.2.

**Alternatives considered**:
- PgBouncer — rejected: asyncpg has built-in pooling. External pooler adds operational complexity for Phase 1.

## Resolved Unknowns

All Technical Context fields resolved. No NEEDS CLARIFICATION items remain.

| Field | Resolution |
|-------|-----------|
| Language/Version | Python 3.11+ (constitution) |
| Primary Dependencies | FastAPI, asyncpg, Alembic, cryptography, bcrypt |
| Storage | PostgreSQL 16 (Docker Compose) |
| Testing | pytest + pytest-asyncio |
| Target Platform | Linux container (Alpine Docker) |
| Project Type | Web service |
| Performance | Prepared statements on 4 hot-path queries |
| Constraints | 25/5, append-only logs, message immutability |
| Scale | 2 → 5 participants without schema change |
