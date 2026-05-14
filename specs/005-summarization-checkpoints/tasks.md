# Tasks: Summarization Checkpoints

> **Status: SHIPPED 2026-04-20 as part of Phase 1.** Task list is historical; outstanding checkboxes were not all carried out as written (scope evolved through PR review).

**Input**: Design documents from `/specs/005-summarization-checkpoints/`

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Create `src/orchestrator/summarizer.py` — SummarizationManager class skeleton

---

## Phase 2: US1 — Checkpoint Trigger (P1)

- [X] T002 [US1] Implement trigger logic in summarizer.py — should_summarize(session) checks (current_turn - last_summary_turn) >= threshold
- [X] T003 [US1] Implement cheapest model selection — find_cheapest_model(participants) returns participant with lowest cost_per_input_token

---

## Phase 3: US2 — Summary Generation (P1)

- [X] T004 [US2] Implement summarization prompt constant — SUMMARIZATION_PROMPT requesting JSON with decisions, open_questions, key_positions, narrative
- [X] T005 [US2] Implement generate_summary — sends accumulated turns + prompt to cheapest model via ProviderBridge, parses JSON response, retries up to 3x on invalid JSON
- [X] T006 [US2] Implement JSON validation — validate_summary_json checks for required keys, defaults missing fields to empty arrays/strings

---

## Phase 4: US3 — Storage (P1)

- [X] T007 [US3] Implement store_summary — persists as message (speaker_type='summary', speaker_id=<session facilitator's participant id> — NOT the literal string 'system'; see FR-005), updates session.last_summary_turn via SessionRepository
- [X] T008 [US3] Add update_last_summary_turn method to SessionRepository in `src/repositories/session_repo.py`

---

## Phase 5: US4 — Cross-Model Fallback (P2)

- [X] T009 [US4] Implement model fallback chain — if cheapest model fails after retries, try next cheapest; if all fail, store raw response as narrative-only with warning logged

---

## Phase 6: Tests

- [X] T010 Write `tests/test_summarizer.py` — test trigger fires at threshold; test trigger does not fire early; test cheapest model selected; test valid JSON parsed; test invalid JSON retried; test fallback to narrative-only; test summary stored as message with correct type; test last_summary_turn updated; test threshold is configurable

---

## Phase 7: Polish

- [X] T011 Update `src/orchestrator/__init__.py` — export SummarizationManager
- [X] T012 Run full test suite (features 001-005) and verify no regressions

---

## Dependencies

- Setup → US1 → US2 → US3 → US4 → Tests → Polish
- MVP: US1 + US2 + US3 (trigger + generate + store)

## Notes

- 12 tasks total — smallest feature yet
- No new dependencies — uses existing ProviderBridge
- Summarization prompt is a constant, not configurable
