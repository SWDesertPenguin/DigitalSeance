# Implementation Plan: Participant Auth & Lifecycle

**Branch**: `002-participant-auth` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-participant-auth/spec.md`

## Summary

Add auth logic on top of the existing data model: bearer token validation with bcrypt, participant approval/rejection, token rotation and revocation, facilitator transfer, token expiry enforcement, session IP binding, and role-based authorization guards. Extends existing repositories (participant_repo, session_repo) and adds new auth service + migration for token_expires_at.

## Technical Context

**Language/Version**: Python 3.11+ (constitution §6.1)
**Primary Dependencies**: asyncpg, bcrypt, cryptography (Fernet) — all already installed
**Storage**: PostgreSQL 16 via Docker Compose (existing)
**Testing**: pytest + pytest-asyncio (existing test harness)
**Target Platform**: Linux container (existing)
**Project Type**: Single project
**Performance Goals**: Token validation < 1 second (bcrypt cost factor 12 ≈ 200ms)
**Constraints**: 25/5 rule, append-only audit logs, fail-closed on missing encryption key
**Scale/Scope**: 2 participants per session Phase 1

## Constitution Check

| Gate | Status | Evidence |
|------|--------|----------|
| **V1 — Sovereignty** | PASS | Tokens per-participant, API keys encrypted, no cross-participant access |
| **V2 — No cross-phase** | PASS | Static tokens only (Phase 1), OAuth deferred to Phase 3 |
| **V3 — Security hierarchy** | PASS | Auth validated before any operation, fail-closed on errors |
| **V4 — Facilitator bounded** | PASS | Facilitator actions restricted to approve/reject/remove/revoke/transfer — cannot read API keys or impersonate |
| **V5 — Transparency** | PASS | All facilitator actions logged to admin audit log |
| **V6 — Graceful degradation** | PASS | Expired tokens get clear errors, not silent failures |
| **V7 — Coding standards** | PASS | 25/5, type hints, pre-commit enforced |
| **V8 — Data security** | PASS | Tokens hashed (bcrypt), keys encrypted (Fernet), plaintext never logged |
| **V9 — Log integrity** | PASS | Admin audit log append-only, all auth actions logged |
| **V10 — AI security** | N/A | No AI content processing in auth layer |
| **V11 — Supply chain** | PASS | No new dependencies added |

## Project Structure

### New/Modified Files

```text
src/
├── auth/
│   ├── __init__.py
│   ├── service.py              # AuthService: validate, rotate, revoke
│   └── guards.py               # Role-based authorization guards
├── repositories/
│   ├── participant_repo.py     # EXTEND: approve, reject, transfer, IP binding
│   └── session_repo.py         # EXTEND: get facilitator_id helper

alembic/versions/
└── 002_add_token_expiry.py     # Add token_expires_at + bound_ip columns

tests/
├── test_auth_service.py        # Token validation, rotation, revocation
├── test_approval.py            # Approve/reject flow, auto-approve
├── test_facilitator.py         # Transfer, role guards
├── test_ip_binding.py          # Session IP binding
└── test_token_expiry.py        # Expiry enforcement
```

### Existing Files to Extend (not replace)

- `src/repositories/participant_repo.py` — add approve, reject, rotate_token, revoke_token, transfer_facilitator, bind_ip methods
- `src/repositories/errors.py` — add TokenExpiredError, TokenInvalidError, AuthRequiredError, NotFacilitatorError, IPBindingMismatchError
- `src/models/types.py` — no changes needed (roles/statuses already defined)
- `tests/conftest.py` — add auth-related fixtures (authenticated participant, facilitator session)

## Complexity Tracking

> No Constitution Check violations. Table intentionally left empty.
