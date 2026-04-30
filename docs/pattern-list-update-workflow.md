# Pattern-list update workflow

How a new red-team incident becomes an updated detection pattern in
`src/security/`. Codifies 007 §FR-017 ("incident → PR within one cycle →
red-team-runbook entry"). Companion to `docs/red-team-runbook.md`
(incident catalog) and `tests/fixtures/adversarial_corpus.txt` (regression
corpus).

Per spec 012 FR-012.

## When this workflow applies

When any of these surfaces a previously-undetected attack pattern:

- Live-incident report from an operator or facilitator
- Adversarial-test session producing a novel evasion
- Published research (LLM jailbreak corpus updates, new prompt-injection class)
- Audit finding from a security review pass
- Provider-disclosed regression (Anthropic / OpenAI / etc. publishing a
  newly-exploitable class)

## The four-step workflow

### 1. Capture the incident

Write the smallest reproducer that demonstrates the attack. Goal is a
single line (or short multi-line block) that today's pipeline does NOT
flag but should. Save it locally — it's about to become a corpus entry.

### 2. Open a PR within one cycle

The PR title format: `fix(007): <attack-class> regression — pattern update`.
Branch: `fix/<short-slug>` per Constitution §14.2.

The PR contains FOUR things, in this order:

1. **Add the reproducer** to `tests/fixtures/adversarial_corpus.txt` under
   the appropriate `# CATEGORY:` heading (or add a new category if the
   attack class is genuinely new).
2. **Add a regression test** asserting the existing detector flags the new
   sample. The test SHOULD FAIL until step 3 lands. (TDD-style; surfaces
   the gap.)
3. **Update the detection pattern** in the relevant `src/security/*.py`
   module — sanitizer, exfiltration, jailbreak, output_validator,
   prompt_protector, or spotlighting. The regression test now passes.
4. **Update `docs/red-team-runbook.md`** with a one-paragraph incident
   entry: date, attack class, the sample, the pattern that closed it,
   and a Round/PR cross-reference.

### 3. Verify zero-regression on the broader corpus

Run the full corpus suite locally:

```bash
pytest tests/test_corpus_fixtures.py -v
```

Confirm:
- The new sample is flagged (your new category passes its detector smoke test)
- The benign corpus still passes the strict 0% FPR guard
- No previously-flagged adversarial sample regresses (other categories still pass)

If the FPR guard trips, your new pattern is too broad. Either narrow the
pattern OR move the offending benign sample to a `# CATEGORY: known-fpr-<topic>`
section with a documented operator-acceptance note.

### 4. Land within one cycle

"One cycle" means: the PR opens within one business day of the incident
landing in someone's inbox AND merges within one calendar week of opening.
Hotfix workflow (Constitution §14.3) applies if the attack is actively
exploited in production.

## What "within one cycle" trades off

The cycle bound is deliberately tight because pattern lists are tested by
attackers more often than by defenders — a slow update cycle lets the same
attack land in multiple sessions before the patch reaches main. We accept
that PRs landing within one cycle may need follow-up tightening (false
positives surface, a more-elegant pattern emerges, etc.) — those follow-
ups land as their own §14.2 amendments, not as blockers on the original
incident closeout.

## Ownership

- **Triage** — facilitator for in-session incidents; operator for live-
  deployment incidents; whoever notices for adversarial-test or audit
  findings.
- **PR author** — the triager OR a delegate; whoever has the bandwidth.
  No formal "security team" exists in Phase 1+2; ownership is whoever-
  notices-fixes. Phase 3 may introduce a named security reviewer role.
- **Reviewer** — at least one reviewer with a security-aware mindset.
  Constitution §14.3 hotfix workflow allows minimum-viable review when
  the attack is actively exploited.

## Cross-references

- Spec 007 §FR-017 — pattern-list update workflow contract
- `docs/red-team-runbook.md` — incident catalog (Round02 Cyrillic
  homoglyph, etc.)
- `tests/fixtures/adversarial_corpus.txt` — regression corpus (lands or
  updates with each pattern PR)
- Constitution §14.2 / §14.3 — bug-fix and hotfix workflows
