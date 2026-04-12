# Implementation Plan: Convergence Detection & Adaptive Cadence

**Branch**: `004-convergence-cadence` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)

## Summary

Add convergence detection (sentence-transformers embeddings, cosine similarity, sliding window), adaptive cadence (similarity-based delay adjustment), adversarial rotation (periodic challenger prompt injection), and multi-signal quality detection (n-gram repetition). Integrates into the existing turn loop from feature 003.

## Technical Context

**Language/Version**: Python 3.11+
**New Dependencies**: sentence-transformers, numpy (for cosine similarity)
**Storage**: PostgreSQL 16 (existing convergence_log table)
**Constraints**: SafeTensors only (no pickle), async embedding (non-blocking), 25/5

## Constitution Check

All gates pass. V10 (AI security) now partially addressed: embedding vectors never exposed via API (FR-016). SafeTensors-only per constitution §6.7.

## Project Structure

### New Files

```text
src/orchestrator/
├── convergence.py       # ConvergenceDetector: embed, compare, flag
├── cadence.py           # CadenceController: delay computation
├── adversarial.py       # AdversarialRotator: counter + prompt injection
├── quality.py           # QualityDetector: n-gram repetition check

tests/
├── test_convergence.py  # US1+2: embedding, similarity, divergence
├── test_cadence.py      # US3: adaptive delay computation
├── test_adversarial.py  # US4: rotation and prompt injection
├── test_quality.py      # US5: n-gram and nonsense detection
```

### Existing Code to Compose

- `src/repositories/log_repo.py` — log_convergence, get_convergence_window
- `src/orchestrator/loop.py` — integrate convergence after each turn
- `src/orchestrator/context.py` — inject divergence/adversarial prompts
