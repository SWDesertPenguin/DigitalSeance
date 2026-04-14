# Tasks: System Prompts & Security Wiring

**Input**: Design documents from `/specs/008-prompts-security-wiring/`

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Create `src/prompts/` directory with `__init__.py`

---

## Phase 2: US1 — 4-Tier System Prompt Assembly (P1)

- [X] T002 [US1] Implement `src/prompts/tiers.py` — assemble_prompt(prompt_tier, custom_prompt) combines low/mid/high/max deltas + custom prompt
- [X] T003 [US1] Embed canary token via PromptProtector integration
- [X] T004 [US1] Write `tests/test_prompt_tiers.py` — test each tier level assembly, custom prompt appending, canary embedding

---

## Phase 3: US2 — Security Pipeline in Context Assembly (P1)

- [X] T005 [US2] Wire sanitize() into `_add_messages` in `src/orchestrator/context.py`
- [X] T006 [US2] Wire spotlight() into `_add_messages` — only for AI messages
- [X] T007 [US2] Write `tests/test_security_wiring.py` — test sanitization applied to all; spotlighting applied to AI only

---

## Phase 4: US3 — Security Pipeline in Turn Loop (P1)

- [X] T008 [US3] Wire output_validator.validate() into `src/orchestrator/loop.py` before persistence
- [X] T009 [US3] Wire filter_exfiltration() into `src/orchestrator/loop.py` before persistence
- [X] T010 [US3] Stage high-risk responses via `_stage_for_review` when validation blocks

---

## Phase 5: Polish

- [X] T011 [P] Update `src/prompts/__init__.py` to export tier helpers
- [X] T012 Run full test suite (features 001-008) to verify no regressions

---

## Phase 6: Canary Hardening (fix/canary-hardening, 2026-04-14)

- [X] T013 Update `src/security/prompt_protector.py` — 3 random 16-char base32 canaries via `secrets`; `canaries` property; `check_leakage` checks all three; accepts `canaries=` kwarg for detection wiring
- [X] T014 Update `src/prompts/tiers.py` — remove `PromptProtector` dependency; `_generate_canaries()` + `_embed_canaries()` embed raw base32 at start/mid/end; no structural wrapper
- [X] T015 Update `src/security/exfiltration.py` — remove HTML-comment canary regex; rename to `_CANARY_LEGACY` (bracket format only)
- [X] T016 Update `tests/` — replace deterministic canary tests with random/3-canary assertions; remove HTML-comment exfiltration test

---

## Dependencies

- Setup → US1, US2, US3 (independent after setup)
- MVP: US1 + US2 + US3 all required for security guarantees

## Notes

- Wiring feature — composes existing security modules (feature 007) into orchestrator
- No new dependencies
- All tasks COMPLETED in PR #45-47
