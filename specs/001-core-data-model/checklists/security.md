# Security Requirements Quality Checklist: Core Data Model

**Purpose**: Validate the quality, clarity, and completeness of security requirements in the Core Data Model spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)
**Sister checklist**: [requirements.md](requirements.md) (general spec completeness — already passed).

Markers used in findings (apply during audit, before resolution):
- `→ ✅` requirement is adequately specified
- `→ ⚠️ partial` spec addresses some aspect but leaves the rest implicit
- `→ ❌ gap` spec silent; code may or may not address it
- `→ 🐛 drift` spec and shipped code disagree
- `→ 📌 accepted` gap is documented in spec already — confirm and re-check

## Requirement Completeness — Encryption at Rest

- [ ] CHK001 Are key-rotation requirements specified for the Fernet master key (rotation cadence, how existing ciphertexts are re-keyed)? [Completeness, Spec §FR-004, Assumptions, Gap]
- [ ] CHK002 Are envelope-encryption migration triggers specified (when does Phase 1 single-key Fernet need to become DEK/KEK)? [Completeness, Spec Assumptions, Gap]
- [ ] CHK003 Are requirements specified for the encryption-key source (env var, secrets manager, KMS) and what fail-closed means at startup? [Completeness, Spec §Edge Cases, partial]
- [ ] CHK004 Is the API-key-overwrite behavior on departure (FR-016) specified at the byte level — random bytes, fixed string, or just "not null"? [Completeness, Spec §FR-016]
- [ ] CHK005 Are requirements specified for backup / replica encryption (does the same Fernet key cover replicas, are backups separately encrypted)? [Completeness, Gap]

## Requirement Completeness — Append-Only Enforcement

- [ ] CHK006 Is "no update or delete operations through the normal application path" (FR-007, FR-008) enforced at the database layer (DB role permissions, RLS, triggers) or only by code discipline? [Completeness, Spec §FR-007, FR-008, Assumptions]
- [ ] CHK007 Are requirements specified for what counts as the "elevated role" that can perform session deletion — single connection pool, separate process, audit before each use? [Completeness, Spec Assumptions]
- [ ] CHK008 Are direct-DBA-access scenarios addressed (a DBA with psql can still UPDATE/DELETE log rows — is that risk acknowledged)? [Completeness, Gap]
- [ ] CHK009 Are append-only requirements specified for `summary_epoch` mutation (the field is set on summarization, but spec doesn't specify whether it's updateable)? [Completeness, Gap]

## Requirement Completeness — Atomic Deletion

- [ ] CHK010 Is the cascade order specified for FR-011 atomic deletion (which child tables go first, what happens if one cascade fails partway)? [Completeness, Spec §FR-011]
- [ ] CHK011 Are requirements specified for the in-flight-query case during deletion (a participant is reading the transcript while it's being deleted)? [Completeness, Edge Case, Gap]
- [ ] CHK012 Is the admin audit log entry for deletion specified at field level (does it record who deleted, when, and a count of removed records)? [Completeness, Spec §FR-019, partial]

## Requirement Completeness — Audit & Retention

- [ ] CHK013 Is "configurable per deployment" (FR-019) specified at the configuration-knob level (env var name, retention policy syntax, automatic purge cadence)? [Completeness, Spec §FR-019]
- [ ] CHK014 Are requirements specified for audit-log integrity (tamper-evident hashing, append-only enforcement at DB layer, cross-row chaining)? [Completeness, Gap]
- [ ] CHK015 Are PII / GDPR / data-subject-deletion requirements addressed (audit log indefinite retention conflicts with right-to-erasure)? [Completeness, Gap]

## Requirement Clarity

- [ ] CHK016 Is "encrypted at rest" (FR-004 / SC-004) defined operationally — encrypted in the row, in TDE, both, neither acceptable? [Clarity, Spec §FR-004]
- [ ] CHK017 Is "irreversible hash" (FR-005) quantified by algorithm + cost factor (cross-ref 002 §FR-A1 bcrypt 12)? [Clarity, Spec §FR-005, cross-ref 002 §FR-A1]
- [ ] CHK018 Is "atomic" (FR-002, FR-011) defined as DB transaction boundary, single SQL statement, or two-phase commit? [Clarity, Spec §FR-002, §FR-011]

## Requirement Consistency

- [ ] CHK019 Does FR-004 ("never appears in plaintext") align with 007 §FR-012 (log scrubbing) — are they enforced by the same mechanism or independent? [Consistency, Spec §FR-004, cross-ref 007 §FR-012]
- [ ] CHK020 Does FR-005 (auth token hashing) align with 002 §FR-001 (bcrypt validation) — single source of truth or duplicated requirements? [Consistency, Spec §FR-005, cross-ref 002 §FR-001]
- [ ] CHK021 Are FR-007 (message immutability) and FR-008 (log immutability) enforced by the SAME mechanism (DB role permissions) or different mechanisms? [Consistency, Spec §FR-007, §FR-008]

## Acceptance Criteria Quality

- [ ] CHK022 Can SC-002 ("no message content alterable") be objectively measured (test fixture trying every CRUD path) or does it require schema audit? [Measurability, Spec §SC-002]
- [ ] CHK023 Is SC-005 ("no orphaned records") testable as an exact post-condition (foreign-key dangling row count = 0) or only approximate? [Measurability, Spec §SC-005]
- [ ] CHK024 Does any SC cover the encryption key unavailability fail-closed (Edge Case mentions it, but no SC measures startup behavior)? [Coverage, Gap]

## Scenario Coverage

- [ ] CHK025 Are recovery requirements defined for partial cascade-deletion failure (some children deleted, parent still exists)? [Coverage, Recovery Flow, Gap]
- [ ] CHK026 Are concurrent-write scenarios addressed beyond turn-number collision (FR-009 referential integrity races during participant deletion)? [Coverage, Gap]
- [ ] CHK027 Are migration-failure scenarios specified (forward-only migrations per Assumptions — what if a migration partially applies and crashes)? [Coverage, Spec Assumptions, Gap]

## Edge Case Coverage

- [ ] CHK028 Are requirements defined for the case where the encryption key changes between writes and reads (e.g., operator rotates the key without re-encrypting old rows)? [Edge Case, Gap]
- [ ] CHK029 Are requirements defined for the case where a participant's API key is encrypted with a key version no longer available (post-rotation)? [Edge Case, Gap]
- [ ] CHK030 Are requirements defined for very long sessions (turn_number int overflow, log table growth, summary epoch exhaustion)? [Edge Case, Gap]
- [ ] CHK031 Are requirements defined for messages whose `parent_turn` references a deleted message (when sub-session branching ships in Phase 3)? [Edge Case, Gap]

## Non-Functional Requirements

- [ ] CHK032 Is the threat model documented and requirements traced to it (NIST SP 800-53 SC-12/SC-13/SC-28/AU-2/AU-3/AU-9; OWASP ASVS V2.10)? [Traceability, Gap]
- [ ] CHK033 Are performance requirements specified for the encryption / decryption path (target latency on dispatch — turn loop assumes negligible overhead)? [Performance, Gap, cross-ref 003 §FR-007]
- [ ] CHK034 Are observability / metrics requirements specified for cascade-deletion duration, encryption errors, integrity-check failures? [Coverage, Gap]

## Dependencies & Assumptions

- [ ] CHK035 Is the dependency on "restricted DB role with INSERT+SELECT only on log tables" (Assumptions) covered by a deployment/migration test that asserts the role's privileges? [Dependency, Spec Assumptions, Gap]
- [ ] CHK036 Is the assumption "Fernet AES-128-CBC + HMAC-SHA256" paired with a re-evaluation trigger (e.g., when AES-128 is deprecated, when CBC mode is found weak, or every N years)? [Assumption, Spec Assumptions, Gap]
- [ ] CHK037 Is the assumption "summarization checkpoint stored as message content field" (vs separate table) acknowledged as an integrity tradeoff (a summary message is mutable per FR-007 only via DB-direct, but its sensitivity is high)? [Assumption, Spec Assumptions]

## Ambiguities & Conflicts

- [ ] CHK038 Does FR-019 ("audit log retained indefinitely by default") conflict with potential data-subject-erasure requirements? Is the conflict resolution documented? [Conflict, Spec §FR-019]
- [ ] CHK039 Is "normal application path" (FR-007, FR-008, SC-002, SC-003) defined precisely so that "abnormal paths" (DBA, migration scripts, debug endpoints) are clearly out-of-scope? [Ambiguity, Spec §FR-007, FR-008]
- [ ] CHK040 Is `domain_tags` storage as serialized array (Assumptions) consistent with referential-integrity guarantees (FR-009) — there's no FK from a serialized array? [Conflict, Spec §FR-009, Assumptions]

## Notes

- Highest-leverage findings to expect: CHK001 / CHK002 (Fernet key rotation lifecycle), CHK006 (whether append-only is DB-enforced or just code discipline — affects whether DBA actions count), CHK014 (audit-log tamper resistance), CHK015 (audit indefinite retention vs erasure rights), CHK032 (no traceability to NIST controls).
- Lower-priority but easy wins: CHK017 (cross-ref 002), CHK019 (cross-ref 007), CHK029 (key-version handling), CHK036 (re-eval trigger).
- Run audit by reading [src/repositories/](../../../src/repositories/) for write paths, [migrations/](../../../migrations/), and the encryption module; cross-reference with this spec's requirements / assumptions / edge cases AND 002 / 007.
