# Contract: Remaining doc deliverables

**Source**: spec FR-010 — covers the doc deliverables whose shape is freeform enough that a separate contract file would be over-specification.

This file consolidates the contract for: `docs/glossary.md`, `docs/retention.md`, `docs/state-machines.md`, `docs/compliance-mapping.md`, `docs/operational-runbook.md`. Each must minimally include the listed sections; structure within sections is at the author's discretion. (The originally-planned authorization-model doc was reclassified to operator-internal per spec FR-010.)

---

## `docs/glossary.md`

**Required**: Alphabetical glossary of project terms. Each entry: 1-3 sentence definition + cross-ref to spec.md(s) where the term is used.

**Initial entry list** (this is the floor, not the ceiling):

MVC floor, convergence, review gate, sponsored AI, spotlighting, datamarking, canary leakage, advisory lock, cadence preset, sprint/cruise/idle, complexity classifier, divergence prompt, adversarial rotation, fail-closed, append-only, tier delta, secure-by-design, override path, narrative-only fallback, fire-and-forget summarization, route-and-assemble-and-dispatch-and-persist, breaker (closed/open), pending/active/paused/removed, held draft, request-id propagation.

**Cross-cutting consumers**: every other doc deliverable.

---

## `docs/retention.md`

**Required sections**:

1. **Per-table inventory**: table name, retention policy (or "indefinite" + rationale), enforcement mechanism (purge job / FK cascade / operator-driven).
2. **Erasure-right (GDPR Art. 17)**: per-participant cascade order across tables.
3. **Retention vs session-deletion**: the 001 §FR-011 atomic-deletion vs §FR-019 audit-log survival pattern documented.
4. **Derived data retention**: summaries, embeddings, tier-text caches.
5. **Backup retention**: separate from live-DB retention; cross-ref backup-encryption ops items.
6. **Retention monitoring / alerting**: thresholds for "purge job stopped working".
7. **Retention env-var inventory**: `SACP_AUDIT_RETENTION_DAYS`, `SACP_SECURITY_EVENTS_RETENTION_DAYS`, future `SACP_USAGE_LOG_RETENTION_DAYS`.

**Tables to inventory** (initial): sessions, participants, messages, branches, routing_log, usage_log, convergence_log, admin_audit_log, security_events, summaries, interrupts, drafts, proposals, votes, invites.

**Cross-cutting consumers**: `docs/compliance-mapping.md`, `docs/operational-runbook.md`.

---

## `docs/state-machines.md`

**Required**: One section per implicit state machine. Per section: states (with terminal states marked), valid transitions (as a table or diagram), invalid transitions (with documented rejection behavior), idempotency rules, source FRs.

**State machines to document**:

1. Session lifecycle (active / paused / archived / deleted) — 001 §FR-010
2. Participant lifecycle (pending / active / paused-manual / paused-breaker / removed) — 002 §FR-005, 003 §FR-015
3. Turn execution (route → assemble → dispatch → persist → log; failure paths) — 003 §FR-019/021/023
4. Review-gate draft (pending → approved / edited / rejected / timed-out / overridden) — 007 §FR-005, FR-006 of THIS feature
5. Circuit breaker (closed / open) — 003 §FR-015
6. Convergence flag (not-converging / converging-detected / divergence-prompted / escalated) — 004 §FR-005-007
7. Proposal voting (open / resolved / abstained) — 001 §FR-013
8. Token lifecycle (issued / active / expired / revoked / rotated) — 002 §FR-001-018
9. Summarization (idle / triggered / in-flight / success / fallback / failure) — 005 §FR-001/006/008
10. WebSocket connection (connecting / authenticated / streaming / reconnecting / closed) — 011 §FR-014
11. Rate-limit bucket (created / active / stale / evicted) — 009 §FR-007
12. Invite token (created / active / consumed / expired / revoked) — 002 + 001 §FR-012

**Cross-cutting consumers**: `docs/ws-events.md`, `docs/operational-runbook.md`, the internal authorization-model doc.

---

## Authorization-model doc (operator-internal)

The originally-planned role × permission matrix doc was reclassified to an operator-internal artifact per spec FR-010; the aggregate matrix concentrates recon value and is not published. Its contract is maintained alongside the artifact itself, off-tree.

---

## `docs/compliance-mapping.md`

**Required sections**:

1. **GDPR article mapping**: Art. 5(c) minimization, Art. 6 lawful basis, Art. 13 information, Art. 15 SAR, Art. 17 erasure, Art. 20 portability, Art. 25 by-design, Art. 28 processor, Art. 30 records, Art. 32 security, Art. 33 breach, Art. 34 subject-notification, Art. 44 transfer.
2. **NIST control mapping**: which CSF / 800-53B / AI 100-2 controls each FR addresses.
3. **AI Act mapping** (where relevant): Art. 10 data governance, Art. 13 transparency.
4. **Per-spec compliance traceability**: aggregates compliance items across 002, 003, 004, 005, 007, 010, 011.

**Cross-cutting consumers**: `docs/retention.md`, the internal authorization-model doc, future regulatory submissions.

---

## `docs/operational-runbook.md`

**Required sections**:

1. **Deploy procedures**: container build, env-var validation step, alembic upgrade, port bind sequence.
2. **Backup / restore**: cadence, retention, restore-validation drill.
3. **Encryption-key rotation**: ceremony when operator must change `SACP_ENCRYPTION_KEY`.
4. **Incident response**: triage path for high false-positive security_events spike, sustained pipeline_error events, canary leakage detected, breach-notification timing.
5. **Tunable runbook**: when to raise / lower each tunable env var (cross-ref `docs/env-vars.md` for the catalog).
6. **Provider degradation playbook**: per-provider partial-outage handling, retry-storm prevention.
7. **Pattern-list update workflow**: cross-ref `docs/pattern-list-update-workflow.md` (FR-012).
8. **Audit follow-through process**: how the local audit-followthrough tracker is maintained (FR-011).
9. **Incident catalog**: cross-ref `docs/red-team-runbook.md`.

**Lands last** (Decision 10 in research.md) as the synthesis of the other deliverables.

---

## CI gate (covers all six docs)

A presence check (no shape validation — these docs are too freeform):

- `scripts/check_doc_deliverables.py` (or extended `check_traceability.py`) verifies that every doc named in FR-010 exists with non-zero size.
- Gate failure means a doc deliverable was renamed/deleted without spec amendment.

## Constitutional references

Each doc gets a §13 entry on land:

```markdown
| `docs/glossary.md` | Terminology | One-place definitions for terms used across specs |
| `docs/retention.md` | Data retention policy | Per-table retention, erasure cascade, backup separation |
| `docs/state-machines.md` | State machine catalog | Per-machine states, transitions, invalid-transition handling |
| `docs/compliance-mapping.md` | Regulatory mapping | GDPR / NIST / AI Act traceability |
| `docs/operational-runbook.md` | Operations playbook | Deploy, restore, rotate, incident response |
```
