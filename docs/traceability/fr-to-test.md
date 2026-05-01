# FR-to-Test Traceability

Per spec 012 FR-003 / `scripts/check_traceability.py`: every FR/SR marker in
each opt-in spec maps to ≥1 named test path, or carries an `untested` tag with
a non-empty trigger note. Specs absent from this file are skipped by the CI
gate (incremental hand-curation per T021).

Format per row: `| FR-NN | test path(s) or `untested: <trigger>` |`

---

## 007-ai-security-pipeline

| FR | Test path(s) | Notes |
|---|---|---|
| FR-001 | tests/test_sanitizer.py, tests/test_corpus_fixtures.py | Every sanitizer pattern group; corpus category coverage |
| FR-002 | tests/test_sanitizer.py, tests/test_007_security_pipeline_testability.py | Round02 Cyrillic homoglyph named regression + homoglyph fold |
| FR-003 | tests/test_spotlighting.py | Spotlighting + same-speaker exemption |
| FR-004 | tests/test_output_validator.py, tests/test_007_security_pipeline_testability.py | Output validation schema contract |
| FR-005 | tests/test_output_validator.py, tests/test_007_security_pipeline_testability.py | Threshold boundary: 0.6 no-block, 0.7 block, 0.9 block |
| FR-006 | tests/test_spotlighting.py | Datamarking layer |
| FR-007 | tests/test_sanitizer.py | ChatML + role markers stripped |
| FR-008 | tests/test_exfiltration.py, tests/test_scrubber.py | Credential pattern detection + log scrubbing |
| FR-009 | tests/test_prompt_protector.py | Canary + fragment leakage detection |
| FR-010 | tests/test_prompt_protector.py | Canary generation and placement |
| FR-011 | untested | LLM-as-judge is NoOpJudge stub; trigger: Phase 3 when feature flag wired |
| FR-012 | tests/test_scrubber.py | Log scrubbing + excepthook traceback scrub |
| FR-013 | tests/test_007_security_pipeline_testability.py | Fail-closed: skip without breaker penalty + pipeline_error row (3 tests) |
| FR-014 | tests/test_007_security_pipeline_testability.py | Timing values are non-negative ints |
| FR-015 | tests/test_007_security_pipeline_testability.py, tests/test_logs.py | Detection-record schema + DB round-trip |
| FR-016 | tests/test_corpus_fixtures.py | 0% FPR on hand-curated benign corpus |
| FR-017 | untested | Pattern-list update is a process item; automated CI gate deferred to Phase 3 |
| FR-018 | untested | LLM-as-judge deferred; trigger: when NoOpJudge replaced in Phase 3 |
| FR-019 | tests/test_corpus_fixtures.py | FPR baseline on benign corpus |
| FR-020 | tests/test_007_security_pipeline_testability.py | layer_duration_ms non-negative on normal + blocked content |
| FR-021 | tests/test_corpus_fixtures.py | Adversarial corpus coverage per category |
| FR-022 | untested | pipeline_total_ms metric deferred to Phase 3 operations audit |
| FR-023 | untested | LLM-as-judge deferred (Phase 3); trigger: when NoOpJudge replaced |
