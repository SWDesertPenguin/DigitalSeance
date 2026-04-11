# Implementation Plan: Core Data Model

**Branch**: `001-core-data-model` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-core-data-model/spec.md`

## Summary

Implement the foundational data persistence layer for SACP Phase 1: 13 database entities (sessions, participants, branches, messages, 4 append-only log types, interrupt queue, review gate drafts, invites, proposals, votes), Alembic migrations, asyncpg connection management, Fernet encryption for API keys at rest, and a repository layer with prepared statements for hot-path queries. No ORM — direct asyncpg with typed dataclass models.

## Technical Context

**Language/Version**: Python 3.11+ (constitution §6.1)
**Primary Dependencies**: FastAPI, asyncpg, Alembic, cryptography (Fernet), bcrypt
**Storage**: PostgreSQL 16 via Docker Compose (constitution §6.2)
**Testing**: pytest + pytest-asyncio (async database tests)
**Target Platform**: Linux container (Alpine-based Docker image, constitution §6.8)
**Project Type**: Web service (MCP server + FastAPI)
**Performance Goals**: 2 concurrent participants per session; prepared statements on hot-path queries (message append, turn fetch, interrupt check, routing log)
**Constraints**: 25-line function cap, 5-argument positional limit, type hints on all signatures (constitution §6.10); append-only logs; message immutability; application-layer API key encryption
**Scale/Scope**: 2 participants Phase 1, schema supports 5 for Phase 3 without migration

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|------|--------|----------|
| **V1 — Sovereignty preserved** | PASS | API keys encrypted at rest (FR-004), never logged. Budget tracked per-participant (FR-003). Model choice stored per-participant. |
| **V2 — No cross-phase leakage** | PASS | Schema includes Phase 3 tables (branches, sub_sessions) for forward compat but spec explicitly defers their exercise. No Phase 2+ features exercised. |
| **V3 — Security hierarchy** | PASS | Encryption before convenience — Fernet key required at startup, fail-closed if absent (edge case 5). Log scrubbing before emission. |
| **V4 — Facilitator powers bounded** | PASS | Admin audit log records all facilitator actions (FR-008). Facilitator cannot read API keys or modify other participants' prompts — enforced by data access layer. |
| **V5 — Transparency maintained** | PASS | Routing log, usage log, convergence log, admin audit log all append-only and queryable (FR-008). |
| **V6 — Graceful degradation** | PASS | Data layer errors surface clearly; no silent data loss. Missing encryption key = fail-closed, not silent skip. |
| **V7 — Coding standards met** | PASS | 25/5 limits enforced by pre-commit hook. Type hints required. Frozen dataclasses for state carriers. |
| **V8 — Data security enforced** | PASS | Tier 1 (secrets): Fernet encryption for API keys, bcrypt for tokens (FR-004, FR-005). Tier 2/3: DB role restrictions. Atomic deletion (FR-011). Key overwrite on departure (FR-016). |
| **V9 — Log integrity preserved** | PASS | Append-only enforcement via DB role (INSERT + SELECT only on log tables). No UPDATE/DELETE through application path (FR-007, FR-008). |
| **V10 — AI security pipeline** | N/A | Data model feature — no AI content processing. Pipeline enforced at orchestrator layer in future features. |
| **V11 — Supply chain controls** | PASS | asyncpg, Alembic, cryptography are well-established packages. Pinned with hash verification via uv.lock. |

**Result**: All applicable gates pass. No violations to track.

## Project Structure

### Documentation (this feature)

```text
specs/001-core-data-model/
├── plan.md              # This file
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: entity definitions + relationships
├── contracts/           # Phase 1: repository interface contracts
│   └── repository.md   # Data access layer contracts
├── quickstart.md        # Phase 1: dev environment setup
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
src/
├── __init__.py
├── config.py                    # Environment variables, settings dataclass
├── database/
│   ├── __init__.py
│   ├── connection.py            # asyncpg pool lifecycle
│   ├── encryption.py            # Fernet encrypt/decrypt for API keys
│   ├── migrations.py            # Alembic runner (programmatic)
│   └── roles.sql                # DB role setup (sacp_app, sacp_cleanup)
├── models/
│   ├── __init__.py
│   ├── types.py                 # Enums: RoutingPreference, SpeakerType, etc.
│   ├── session.py               # Session, Branch frozen dataclasses
│   ├── participant.py           # Participant frozen dataclass
│   ├── message.py               # Message frozen dataclass
│   └── logs.py                  # RoutingLog, UsageLog, ConvergenceLog, AdminAuditLog
├── repositories/
│   ├── __init__.py
│   ├── base.py                  # BaseRepository (pool reference, helpers)
│   ├── session_repo.py          # Session + Branch CRUD + lifecycle
│   ├── participant_repo.py      # Participant CRUD + departure
│   ├── message_repo.py          # Message append + query (prepared statements)
│   ├── log_repo.py              # All 4 log types (INSERT + SELECT only)
│   ├── interrupt_repo.py        # Interrupt queue operations
│   ├── review_gate_repo.py      # Review gate draft lifecycle
│   ├── invite_repo.py           # Invite CRUD + redemption
│   └── proposal_repo.py         # Proposal + Vote operations

alembic/
├── alembic.ini
├── env.py
└── versions/
    └── 001_initial_schema.py    # All 13 tables + constraints + indexes

tests/
├── conftest.py                  # Fixtures: test DB, pool, seed data
├── test_session_crud.py         # US1: Session creation + defaults
├── test_participant.py          # US2: Join + config + encryption
├── test_messages.py             # US3: Append + immutability + tree
├── test_logs.py                 # US4: Append-only enforcement
├── test_lifecycle.py            # US5: Status transitions + atomic delete
├── test_interrupt_queue.py      # US6: Priority delivery + FIFO
├── test_review_gate.py          # US7: Draft lifecycle (approve/edit/reject/timeout)
├── test_invites.py              # US8: Hash + limits + expiry
├── test_proposals.py            # US9: Voting + acceptance modes
└── test_encryption.py           # Fernet roundtrip + fail-closed
```

**Structure Decision**: Single-project layout. No frontend in Phase 1 (constitution §10). FastAPI app entry point (`src/main.py`) deferred to a later feature — this feature delivers the data layer only.

## Complexity Tracking

> No Constitution Check violations. Table intentionally left empty.
