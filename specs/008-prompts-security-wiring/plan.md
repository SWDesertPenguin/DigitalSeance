# Implementation Plan: System Prompts & Security Wiring

**Branch**: `008-prompts-security-wiring` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)

## Summary

Wire the 4-tier delta system prompt assembly and the AI security pipeline into the existing turn loop and context assembly. System prompts are assembled from four tiers (low/mid/high/max) with canary tokens and context markers. The security pipeline (sanitization, spotlighting, output validation, exfiltration filtering) is integrated into context assembly (input side) and turn loop (output side).

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: N/A
**Storage**: N/A
No new dependencies. Wires existing security modules (feature 007) and prompt tiers into the orchestrator (features 003, 006).

## Constitution Check

All gates pass. 4-tier prompts enforce collaboration framing (V1). Canary tokens detect prompt extraction (V10). Context markers maintain trust boundaries (V8).

## Project Structure

### New Files

```text
src/prompts/
├── __init__.py
├── tiers.py             # 4-tier delta assembly (low/mid/high/max)
├── canary.py            # Canary token generation and embedding

tests/
├── test_prompt_tiers.py     # US1: tier assembly
├── test_security_wiring.py  # US2-US3: pipeline integration
├── test_canary.py           # Canary token stripping
```

## Complexity Tracking

> No Constitution Check violations.
