# Implementation Plan: Debug Export

**Branch**: `fix/live-test-feedback` (bundled) | **Date**: 2026-04-15 | **Spec**: [spec.md](spec.md)

## Summary

A single read-only endpoint `GET /tools/debug/export` that returns everything the server knows about a session as one JSON blob. Facilitator-only. Stripped of secrets. Intended for operator troubleshooting, not for participant consumption.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: FastAPI (existing), asyncpg (existing)
**Storage**: Reads only — no schema changes
**Project Type**: Single project

## Constitution Check

- V1 (Sovereignty): Facilitator-scoped, session-scoped. No cross-session leakage.
- V5 (Observability): This feature *is* observability. Exposes routing, convergence, and usage logs that previously required DB access.
- V7 (Security): Sensitive fields (encrypted API keys, token hashes, bound IPs, provider keys, DB URL, encryption key) are excluded at the serializer boundary, not hoped away downstream.

## Project Structure

### New Files

```text
src/mcp_server/tools/
├── debug.py              # GET /tools/debug/export endpoint + scrubbers

specs/010-debug-export/
├── spec.md
├── plan.md
└── tasks.md
```

### Modified Files

```text
src/mcp_server/app.py     # register debug_router
tests/test_mcp_e2e.py     # two e2e tests (facilitator happy-path + 403 for participant)
```

## Complexity Tracking

> No Constitution Check violations. No new dependencies. One new endpoint, ~150 LOC.
