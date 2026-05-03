# Tasks: Convergence Detection & Adaptive Cadence

> **Status: SHIPPED 2026-04-20 as part of Phase 1.** Task list is historical; outstanding checkboxes were not all carried out as written (scope evolved through PR review).

**Input**: Design documents from `/specs/004-convergence-cadence/`

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Add `sentence-transformers>=3.0.0` and `numpy>=1.26.0` to pyproject.toml
- [X] T002 [P] Create `src/orchestrator/quality.py` — QualityDetector with n-gram repetition check (detect_repetition returns bool + score)

---

## Phase 2: Foundational

- [X] T003 Implement `src/orchestrator/convergence.py` — ConvergenceDetector: load model (SafeTensors only), compute_embedding (async wrapper), compute_similarity (cosine vs sliding window), detect_convergence (threshold check), inject_divergence_prompt
- [X] T004 [P] Implement `src/orchestrator/cadence.py` — CadenceController: compute_delay (from similarity + preset), reset_on_interjection, get_current_delay; presets: sprint (2s-15s), cruise (5s-5m), idle (trigger-only)
- [X] T005 [P] Implement `src/orchestrator/adversarial.py` — AdversarialRotator: should_inject (counter check), get_prompt (constant text), advance (increment counter, rotate participant index), reset

---

## Phase 3: User Story 1 — Convergence Detection (Priority: P1) MVP

- [X] T006 [US1] Write `tests/test_convergence.py` — test embedding stored in convergence log; test high similarity flagged; test low similarity not flagged; test async (non-blocking); test window smaller than configured uses available turns
- [X] T007 [US1] Integrate convergence detector into `src/orchestrator/loop.py` — call after message persistence, log to convergence_log via LogRepository

---

## Phase 4: User Story 2 — Divergence Prompt (Priority: P1)

- [X] T008 [US2] Extend `tests/test_convergence.py` — test divergence prompt injected on sustained convergence; test escalation on continued convergence; test clearance when divergence succeeds; test divergence_prompted flag logged
- [X] T009 [US2] Extend convergence detector — add divergence state tracking (prompted, escalated) and integration with context assembler for prompt injection

---

## Phase 5: User Story 3 — Adaptive Cadence (Priority: P2)

- [X] T010 [US3] Write `tests/test_cadence.py` — test low similarity → low delay; test high similarity → high delay; test interjection resets to floor; test sprint preset bounds; test cruise preset bounds; test idle preset fires only on trigger
- [X] T011 [US3] Integrate cadence into turn loop — compute delay after convergence check, apply via asyncio.sleep

---

## Phase 6: User Story 4 — Adversarial Rotation (Priority: P2)

- [X] T012 [US4] Write `tests/test_adversarial.py` — test prompt injected at interval; test rotation across participants; test skips paused participants; test logged to routing log
- [X] T013 [US4] Integrate adversarial rotator into turn loop — check counter before routing, inject prompt into context when triggered

---

## Phase 7: User Story 5 — Quality Detection (Priority: P3)

- [X] T014 [US5] Write `tests/test_quality.py` — test excessive repetition flagged; test normal text passes; test empty content flagged
- [X] T015 [US5] Integrate quality detector into convergence assessment — combine n-gram score with embedding similarity

---

## Phase 8: Polish

- [X] T016 [P] Update `src/orchestrator/__init__.py` — export ConvergenceDetector, CadenceController, AdversarialRotator, QualityDetector
- [X] T017 Run full test suite (features 001-004) and verify no regressions

---

## Phase 9: FR-020 Information-density signal (audit fix/quality-density-signal, 2026-05-03)

- [X] T018 Implement `src/orchestrator/density.py` — compute_density (text + embedding → score), is_anomaly (compares to rolling baseline), update_baseline, get_threshold_ratio (env var with V6 fallback)
- [X] T019 Wire `ConvergenceDetector._maybe_log_density` into `process_turn` after embedding compute; reuse the same float32 array via `np.frombuffer`
- [X] T020 Schema migration `alembic/versions/010_density_signal.py` — convergence_log: tier column + nullable embedding/similarity + density/baseline columns + extended PK; sessions: density_baseline_window REAL[] column
- [X] T021 Mirror schema in `tests/conftest.py` raw DDL
- [X] T022 LogRepository.{log_density_anomaly, get_density_baseline, update_density_baseline}; filter `_CONVERGENCE_WINDOW_SQL` to `tier='convergence'`
- [X] T023 V16 validator `validate_density_anomaly_ratio` for SACP_DENSITY_ANOMALY_RATIO; register in VALIDATORS tuple; document in docs/env-vars.md
- [X] T024 Unit tests `tests/test_density.py` for compute_density, is_anomaly, update_baseline, threshold env handling
- [X] T025 Integration tests `tests/integration/test_density_signal.py` — 25-turn synthetic session; baseline update; no-anomaly-before-baseline; anomaly logged after baseline; window cap; convergence/density tier separation
- [X] T026 Calibration emit `tests/calibration/test_density_distribution.py` — runs density across benign + adversarial fixtures, writes `density_distribution.json` artifact for Phase 3 retuning
- [X] T027 V16 startup tests in `tests/test_config_validators.py` for SACP_DENSITY_ANOMALY_RATIO

---

## Dependencies

- Setup → Foundational → US1 → US2 → US3/US4 (parallel) → US5 → Polish
- MVP: US1 + US2 (convergence + divergence)

## Notes

- 17 tasks total — smaller feature than 003
- sentence-transformers model loaded once at startup, reused
- SafeTensors format enforced — no pickle
- All convergence operations async (non-blocking)
