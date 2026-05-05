# Pattern-list update workflow

> Canonical workflow for promoting a red-team incident or production false-negative
> into a durable detection pattern in `src/security/`. Implements the contract of
> 007 spec.md §FR-017 ("pattern lists are the canonical source of truth; new
> attack patterns surfaced in shakedowns, red-team exercises, or production
> incidents MUST be added within one PR cycle").

**Audience**: contributors landing detector changes; operators triaging a
false-negative; reviewers gating pattern-list PRs.
**Companion docs**: `docs/red-team-runbook.md` (incident catalog),
`docs/operational-runbook.md` §7 (operator-facing summary),
`tests/fixtures/adversarial_corpus.txt` + `tests/fixtures/benign_corpus.txt`
(regression-test surface).

---

## When this workflow applies

Any of the following is a trigger:

1. A red-team shakedown produces a payload the existing pipeline does not catch.
2. A production `security_events` query surfaces a category of attack absent from
   the patterns.
3. An upstream provider releases a model that responds to a previously-blocked
   prompt class differently (regression risk).
4. A dependency change (LiteLLM, sentence-transformers, the unicode database)
   alters how an existing pattern matches.

Out of scope: general detector tuning unrelated to a specific incident; that
goes through normal feature work per Constitution §14.1.

---

## The four-step workflow

Each pattern-list PR MUST complete all four steps within a single PR cycle.
Splitting steps across PRs is the failure mode this workflow exists to prevent
(corpus added without pattern; pattern added without regression test; runbook
left stale).

### Step 1 — Capture the incident

- Add the offending payload to `tests/fixtures/adversarial_corpus.txt` under
  the appropriate `# CATEGORY:` header. If no category fits, create one and add
  a brief justification to the corpus's top comment block.
- For an incident discovered via shakedown, append a numbered entry to the
  relevant section of `docs/red-team-runbook.md` with the payload, expected
  defender behavior, and the verify line (log table / DOM element / WS close
  code) that proves pass/fail.
- For a production incident, capture the trigger in the PR description with the
  `security_events` row (or `routing_log` row, or operator-supplied transcript
  with PII redacted).

### Step 2 — Add the regression test

- Extend `tests/test_corpus_fixtures.py` (or the relevant detector test module)
  so the new corpus entry is exercised against its detector. If a new category
  was introduced, add the structural assertion that the category exists with at
  least one sample.
- If the incident exposed a property the existing tests did not assert (e.g.,
  case-insensitivity, NFKC normalization, multi-line spanning), add a
  property-level test alongside the corpus-driven one.
- The new test MUST fail against the current `main` and pass against the
  patched code. Demonstrating the failing-then-passing state in the PR
  description is the easiest way to satisfy reviewer scrutiny.

### Step 3 — Update the pattern list

- Edit the relevant module under `src/security/` (sanitizer, exfiltration,
  jailbreak, output_validator, scrubber, prompt_protector). Keep the change
  scoped: one incident, one pattern, one PR.
- Run the full unit suite locally (`pytest tests/unit/`). The PR MUST NOT
  introduce a false positive against `tests/fixtures/benign_corpus.txt`. If a
  benign-corpus assertion fails, the pattern is too broad — narrow it before
  proceeding.
- For pattern modules that compile regexes at import time, verify the new
  regex compiles by running the orchestrator's startup path locally (or
  `python -m src.config` if the validators path is reachable). 007 §FR-013
  guarantees fail-closed on compile errors at startup, but a CI-only failure
  wastes the reviewer's time.

### Step 4 — Update the runbook entry and land

- Mark the red-team-runbook entry from Step 1 as `PASS` for the patched
  pipeline, with a date and the session id of the verifying run.
- Note the closing PR number in the runbook entry so future readers can trace
  pattern → fix → regression test.
- Land the PR. The full cycle (capture through merge) MUST complete within one
  PR cycle (typically <= 7 days). A PR that stalls past the cycle is escalated
  to the facilitator per the on-call procedure documented in
  `docs/operational-runbook.md` §4.

---

## Ownership

- **Pattern modules** (`src/security/sanitizer.py`,
  `src/security/exfiltration.py`, `src/security/jailbreak.py`,
  `src/security/output_validator.py`, `src/security/scrubber.py`,
  `src/security/prompt_protector.py`): owned by the contributor closing the
  PR. Code review by the facilitator or a designated security-aware reviewer
  is required before merge.
- **Corpus files** (`tests/fixtures/`): same ownership as pattern modules; a
  pattern-list PR landing without a corpus update is a process violation.
- **Runbook** (`docs/red-team-runbook.md`): updated in the same PR. Stale
  runbook entries (PASS recorded but no patching PR linked) are flagged in
  the next constitution-adherence audit.

---

## Cadence

This workflow is incident-driven, not scheduled. Pattern-list reviews happen:

- Per PR (the workflow itself).
- At Phase boundaries (per `docs/threat-model-review-process.md`), as part of
  pruning obsolete entries and confirming coverage of newly supported providers
  per 007 §FR-017's Phase-boundary review clause.

There is no monthly / quarterly cadence. The corpora are the canonical
regression surface; if the corpora pass and benign FPR is within budget, the
pattern set is current.

---

## Out of scope for this workflow

- **Schema changes** to `security_events` or `routing_log` (those go through
  alembic migrations + the schema-mirror gate).
- **Detector architecture changes** (replacing pattern matching with an ML
  classifier, adding a new layer to the pipeline) — those are feature work
  per Constitution §14.1.
- **Operator-facing alerting tuning** (`security_events` rate thresholds,
  Grafana dashboards) — those live in `docs/operational-runbook.md` §4 and
  are not a pattern-list concern.

---

## References

- 007 spec.md §FR-017 — the binding requirement this workflow implements
- 007 spec.md §FR-019 / §FR-021 — false-positive and adversarial coverage
  targets the regression tests measure against
- `docs/red-team-runbook.md` — incident catalog
- `docs/operational-runbook.md` §4 (incident response), §7 (this workflow's
  operator-facing summary)
- `docs/threat-model-review-process.md` — Phase-boundary review trigger
- Constitution §10 (phase boundaries), §14.7 (audit work category),
  §13 (authoritative references)
