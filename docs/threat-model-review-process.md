# Threat-model freshness review process

When and how the SACP threat model gets re-reviewed. Threats evolve;
without an explicit cadence the threat-model traceability tables in each
spec (added during the 11-spec security audit, PR #157) drift away from
the actual attack surface. This doc codifies a bounded review cadence
plus trigger-based reviews for in-Phase incidents.

Per spec 012 FR-016 / research.md Decision 9.

## What "the threat model" means here

The threat model is the union of:

- Per-spec "Threat model traceability" tables in `specs/NNN/spec.md`
  (added in PR #157 across all 11 specs)
- `docs/AI_attack_surface_analysis_for_SACP_orchestrator.md` — the
  13-attack-vector analysis with mitigations and standards mappings
- `docs/red-team-runbook.md` — the live incident catalog
- The Constitution §8 (AI-specific security) and §9 (security boundaries)
  enumeration of defense layers

A review re-checks all four sources for drift against current code, current
threat-intel, and any incidents accumulated since the last review.

## Cadence: per-Phase-boundary

A full review runs at every Phase boundary (Phase 2 → Phase 3,
Phase 3 → Phase 4, etc.). Phase boundaries are already constitutional
milestones (§10) — adding threat-model checkpoints to them adds no
new ceremony.

A full review covers:

1. **Per-spec traceability tables** — for each spec, do the FRs still map
   to the right OWASP / NIST / ASVS / GDPR controls? Did any FR change
   semantics in a way that invalidates its threat mapping?
2. **Attack surface analysis** — is the 13-vector list still complete?
   Have any new vectors emerged from incidents (red-team-runbook), provider
   ecosystem shifts (litellm major versions), or research?
3. **Constitution §8 and §9** — do the listed defense layers still match
   shipped code? Are any defenses listed as "Phase 1+2 status: deferred"
   now ready to land?
4. **Incident retrospective** — for every red-team-runbook entry since
   the prior review, was the response within the workflow expected
   cycle (per `docs/pattern-list-update-workflow.md`)? Are there
   patterns across incidents (clusters by attack class, by participant
   role, by topology)?

Output: an updated set of spec amendments + Constitution amendments + a
Phase-boundary closeout note in the relevant Sync Impact Report.

## Triggers: in-Phase reviews

A full Phase-boundary review is too coarse for fast-moving threats. The
following events trigger a partial (single-surface) review without
waiting for the next Phase boundary:

### Trigger 1: New red-team incident category

Any red-team incident that does NOT fit an existing `tests/fixtures/adversarial_corpus.txt`
category triggers:

- A new `# CATEGORY:` in the corpus
- A new `_*_PATTERN` group (or detector module) in `src/security/`
- A re-check of every spec's threat-model table for the new attack class
- A new entry in the attack surface analysis if the class is novel

### Trigger 2: New participant-side capability

When a new topology, role, or cross-organizational pattern lands (e.g.,
topology 7 MCP-to-MCP arriving in Phase 3), the threat model is
re-reviewed against the new capability:

- What new boundaries does the capability introduce?
- What existing defenses no longer cover the new path?
- What capability-specific defenses are required?

### Trigger 3: Dependency major version with new attack surface

When a security-critical dependency lands a major version that introduces
a new attack class — `litellm` major-version bumps, `cryptography`
package CVEs, `fastapi` or `asyncpg` security advisories — re-review the
relevant spec's traceability table and the attack surface analysis for
new mitigation requirements.

### Trigger 4: Provider-disclosed regression

When Anthropic / OpenAI / Google / etc. publish a notice describing a
newly-exploitable class of prompt-injection or jailbreak — typically via
their model-card updates or security advisories — re-review 007 (AI
security pipeline) and 008 (prompts security wiring) for coverage.

## Ownership

- **Phase-boundary review** — facilitator schedules the session within
  two weeks of declaring a Phase boundary; security-aware reviewer in
  the loop. Output amendments land as a single PR per affected spec.
- **Trigger-based review** — whoever notices the trigger event opens a
  triage issue or PR within one business day of the trigger. The §14.2
  bug-fix workflow applies (or §14.3 hotfix if actively exploited).
- **Catalog maintenance** — keeping
  `docs/AI_attack_surface_analysis_for_SACP_orchestrator.md` and
  `docs/red-team-runbook.md` synchronized is a continuous process; not
  gated on a formal review.

## What this process is NOT

- NOT an annual schedule — Phase boundaries vary, but the cadence is
  "per-boundary," not "per-year." A long Phase still gets one review.
- NOT a per-PR review — that's covered by the §14.2 bug-fix workflow's
  spec-update requirement when behavior changes.
- NOT a separate threat-modeling sub-team — the project doesn't have one
  in Phase 1+2. The reviewer is whoever has security context plus the
  facilitator. Phase 3 may introduce a named security-review role.

## Cross-references

- Constitution §8 (AI-specific security), §9 (security boundaries), §10
  (Phase boundaries)
- Spec 007 §FR-017 — pattern-list update workflow
- `docs/AI_attack_surface_analysis_for_SACP_orchestrator.md` — the
  13-vector analysis baseline
- `docs/red-team-runbook.md` — incident catalog
- `docs/pattern-list-update-workflow.md` — incident-to-pattern workflow
