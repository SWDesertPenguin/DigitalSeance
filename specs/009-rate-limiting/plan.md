# Implementation Plan: Rate Limiting

**Branch**: `009-rate-limiting` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)

## Summary

Per-participant rate limiting middleware for the MCP server: in-memory sliding window counters, 60 requests/minute default, 429 responses with Retry-After header, per-IP global cap as DoS backstop. Integrates as FastAPI middleware into the existing MCP server (feature 006).

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: N/A
**Storage**: N/A
No new dependencies. In-memory rate counters with FastAPI middleware.

## Constitution Check

All gates pass. Per-participant limits respect sovereignty (V1). Rate limiting is transparent via Retry-After headers (V5). Global IP cap prevents DoS without penalizing individual participants (V6).

## Project Structure

### New Files

```text
src/mcp_server/
├── rate_limiter.py      # Sliding window per-participant + per-IP counters

tests/
├── test_rate_limiter.py # US1: per-participant limits, 429 responses
```

## Complexity Tracking

> No Constitution Check violations.
