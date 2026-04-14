# Implementation Plan: Summarization Checkpoints

**Branch**: `005-summarization-checkpoints` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)

## Summary

Add periodic summarization checkpoints to the turn loop: trigger every N turns, generate structured JSON summaries via the cheapest available model, store as immutable messages, and update session state. Composes existing ProviderBridge and MessageRepository.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: N/A
**Storage**: PostgreSQL 16 (existing)
No new dependencies. Uses existing LiteLLM bridge (feature 003) and message storage (feature 001).

## Constitution Check

All gates pass. Summaries stored as immutable messages (V9). Cheapest model selection respects sovereignty (V1).

## Project Structure

### New Files

```text
src/orchestrator/
├── summarizer.py        # SummarizationManager: trigger, generate, store

tests/
├── test_summarizer.py   # Trigger, JSON parsing, fallback, storage
```

### Existing Code to Compose

- `src/api_bridge/provider.py` — dispatch_with_retry
- `src/repositories/message_repo.py` — append_message, get_summaries
- `src/repositories/session_repo.py` — get_session (for last_summary_turn)
- `src/repositories/participant_repo.py` — list_participants (for cheapest model)
