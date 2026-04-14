# Implementation Plan: MCP Server

**Branch**: `006-mcp-server` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)

## Summary

FastAPI application serving SSE on port 8750 with bearer token auth middleware, participant and facilitator tool endpoints, session lifecycle management, turn loop control, and session export. Composes all five prior features into a unified HTTP interface.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: FastAPI, uvicorn (existing)
**Storage**: PostgreSQL 16 (existing)
**Project Type**: Single project
No new dependencies. FastAPI + uvicorn already in pyproject.toml.

## Constitution Check

All gates pass. Auth gating enforces sovereignty (V1). All actions logged (V5, V9). Facilitator powers bounded by role checks (V4).

## Project Structure

### New Files

```text
src/mcp_server/
├── __init__.py
├── app.py               # FastAPI app, SSE endpoint, lifespan
├── middleware.py         # Bearer token auth dependency
├── tools/
│   ├── __init__.py
│   ├── participant.py   # inject, history, status, config, rotate
│   ├── facilitator.py   # invite, approve, reject, remove, revoke, transfer
│   └── session.py       # create, pause, resume, archive, start/stop loop, export

tests/
├── test_mcp_app.py      # App startup, SSE connection
├── test_mcp_tools.py    # Tool endpoint tests
├── test_mcp_auth.py     # Auth middleware rejection
```

### Existing Code to Compose

All 5 prior features: AuthService, ConversationLoop, repositories, config
