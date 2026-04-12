# Tasks: AI Security Pipeline

**Input**: Design documents from `/specs/007-ai-security-pipeline/`

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 Create `src/security/` directory with `__init__.py`

---

## Phase 2: US1 — Context Sanitization (P1)

- [ ] T002 [US1] Implement `src/security/sanitizer.py` — sanitize(text) strips ChatML tokens, role markers, HTML comments, override phrases, invisible Unicode; returns cleaned text
- [ ] T003 [US1] Write `tests/test_sanitizer.py` — test each pattern type stripped; test clean text unchanged; test combined patterns; test empty input
- [ ] T004 [US1] Integrate sanitizer into `src/orchestrator/context.py` — call sanitize() on message content in _add_messages before appending

---

## Phase 3: US2 — Inter-Agent Spotlighting (P1)

- [ ] T005 [US2] Implement `src/security/spotlighting.py` — spotlight(content, source_id) applies word-level datamarking with source hash prefix; only applied to AI-type messages
- [ ] T006 [US2] Write `tests/test_spotlighting.py` — test datamarks inserted; test original content recoverable; test human messages not marked; test system messages not marked
- [ ] T007 [US2] Integrate spotlighting into `src/orchestrator/context.py` — apply spotlight() to AI messages in _add_messages before appending

---

## Phase 4: US3 — Output Validation (P1)

- [ ] T008 [US3] Implement `src/security/output_validator.py` — validate(text) checks for injection markers, returns risk_score + findings list; high risk → flagged for review
- [ ] T009 [US3] Write `tests/test_output_validator.py` — test injection markers flagged; test clean text passes; test risk score reflects severity; test findings list populated
- [ ] T010 [US3] Integrate validator into `src/orchestrator/loop.py` — call validate() after dispatch, before persist; if high risk, stage for review instead of persisting

---

## Phase 5: US4 — Exfiltration Filtering (P2)

- [ ] T011 [US4] Implement `src/security/exfiltration.py` — filter_exfiltration(text) strips markdown images, flags data-embedding URLs, redacts credential patterns (sk-*, eyJ*, etc.)
- [ ] T012 [US4] Write `tests/test_exfiltration.py` — test markdown image stripped; test data URLs flagged; test API key redacted; test JWT redacted; test normal URLs unchanged

---

## Phase 6: US5 — Jailbreak Detection (P2)

- [ ] T013 [US5] Implement `src/security/jailbreak.py` — check_jailbreak(text, participant_avg_length) checks length deviation, known phrases, non-existent participant refs, meta-commentary
- [ ] T014 [US5] Write `tests/test_jailbreak.py` — test extreme length flagged; test known phrases flagged; test normal response passes

---

## Phase 7: US6 — Prompt Extraction Defense (P2)

- [ ] T015 [US6] Implement `src/security/prompt_protector.py` — PromptProtector with canary token embedding and fragment scanning; check_leakage(response) returns bool
- [ ] T016 [US6] Write `tests/test_prompt_protector.py` — test canary token detected; test 25-word fragment detected; test clean response passes

---

## Phase 8: US7 — Log Scrubbing (P3)

- [ ] T017 [US7] Implement `src/security/scrubber.py` — scrub(text) redacts API key patterns, JWTs, Fernet tokens; install as logging filter
- [ ] T018 [US7] Write `tests/test_scrubber.py` — test API key redacted; test JWT redacted; test clean text unchanged

---

## Phase 9: Polish

- [ ] T019 [P] Update `src/security/__init__.py` — export all security modules
- [ ] T020 Run full test suite (features 001-007) and verify no regressions

---

## Dependencies

- Setup → US1 → US2 → US3 (pipeline builds sequentially)
- US4, US5, US6 can run in parallel after US3
- US7 independent
- MVP: US1 + US2 + US3 (sanitize + spotlight + validate)

## Notes

- 20 tasks
- No new dependencies — pure Python
- Performance target: <50ms for full pipeline
- 25/5 coding standards apply to all security modules
