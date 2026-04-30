# Compliance Requirements Quality Checklist: Core Data Model

**Purpose**: Validate the quality, clarity, and completeness of compliance requirements in the Core Data Model spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 6 items pass cleanly, 24 have findings. Compliance for SACP centers on: (1) GDPR right-to-erasure vs. audit-log retention (the FR-019 denormalized snapshot is a direct compromise on Article 17), (2) encryption-at-rest scope (Phase 1 covers only API keys; other sensitive fields trust DB ACL), (3) data-residency / cross-border (unspecified), (4) lawful-basis tracking (unspecified). Spec is honest about scope (Phase 1 vs. Phase 3 deferrals are documented) but doesn't map any FR to a named regulatory regime, leaving compliance posture implicit.

## Regulatory Mapping

- [x] CHK001 Are target regulatory regimes named (GDPR, CCPA, HIPAA, SOC 2, ISO 27001, FedRAMP)?
  [GAP]. Spec is silent on which regime(s) the data model is designed to satisfy. Threat-model traceability table (added at audit closeout) maps to OWASP / NIST controls but not to data-protection law.

- [x] CHK002 Is the lawful basis for processing (GDPR Article 6) tracked per participant or session (consent, contract, legitimate interest)?
  [GAP]. No `lawful_basis` field on `participants`. Use cases like consulting (Constitution §1) imply contractual basis; debate may imply consent. Not codified.

- [x] CHK003 Is data classification specified per column (e.g. PII, sensitive PII, operational metadata)?
  [PARTIAL]. FR-020 names "operational metadata" as the assumed classification for unencrypted fields. Per-column classification matrix would make encryption-scope decisions reviewable.

- [x] CHK004 Is data residency / cross-border transfer specified?
  [GAP]. PostgreSQL deployment is operator-managed, but participant API keys leave the deployment via `litellm` to (e.g.) Anthropic / OpenAI / Google APIs — that's a transfer to a third-party processor with cross-border implications.

- [x] CHK005 Is processor / sub-processor disclosure required (which LLM providers received which content)?
  [PARTIAL]. `routing_log` records which provider got each call (per turn) — this IS a processor record. Spec doesn't surface it as a compliance artifact.

## Right to Erasure (GDPR Art. 17)

- [x] CHK006 Is the FR-011 atomic session deletion vs. FR-019 audit-log retention contradiction acknowledged as a documented compromise?
  [PARTIAL]. FR-019 explicitly justifies the audit row surviving deletion (forensic record) but the spec doesn't frame this as a GDPR Art. 17 trade-off requiring legal-basis documentation (legitimate interest in audit trail vs. erasure right). Operators may need to disclose this in their DPIA.

- [x] CHK007 Is the `SACP_AUDIT_RETENTION_DAYS` mechanism (FR-019) specified to actually purge expired rows, or is it advisory?
  [GAP]. FR-019 says "MAY be overridden via env var" but doesn't pin a purge job. Without an enforcing scheduler, the env var is decorative.

- [x] CHK008 Is participant deletion (`FR-016` overwrite api_key + invalidate token) sufficient for "right to be forgotten" in messages they authored?
  [GAP]. Messages they sent remain in `messages` (FR-007 immutability). Their `display_name` and content are still attributable. GDPR-strict erasure would require either pseudonymization on departure or mass-redact of authored content.

- [x] CHK009 Is the de-identification path specified (e.g. tombstone the participant row but anonymize their authored messages)?
  [GAP].

- [x] CHK010 Are subject-access-request (GDPR Art. 15) export requirements specified — what data does a participant get when they ask "what do you have on me"?
  [PARTIAL]. 010 §debug-export is facilitator-only (FR-2). No participant-self-service export path. SAR fulfillment requires manual operator query.

- [x] CHK011 Is the response window for SAR / erasure requests bounded (GDPR's 30-day default)?
  [GAP].

## Encryption Scope

- [x] CHK012 Is the Phase 1 encryption-at-rest scope (FR-020: only `participants.api_key_encrypted`) cross-referenced to a documented threat model that justifies the omission of `system_prompt`, `display_name`, message content?
  [PARTIAL]. FR-020 documents the scope and trigger ("any deployment that stores material classified higher than 'operational metadata'"). What's missing: explicit risk register for what's exposed in DB-dump scenarios.

- [x] CHK013 Is key management lifecycle specified (generation, distribution, rotation, escrow, revocation)?
  [PARTIAL]. FR-021 says rotation is NOT supported in Phase 1. Generation, distribution, escrow are all unspecified.

- [x] CHK014 Are encryption-at-transit requirements specified for the database connection?
  [GAP]. PostgreSQL TLS is operator-controlled; spec doesn't mandate `sslmode=require` for asyncpg.

- [x] CHK015 Is the cryptographic algorithm (Fernet = AES-128-CBC + HMAC-SHA256) named and FIPS / NIST-approved?
  [PARTIAL]. Fernet is named in FR-020 but not mapped to FIPS 140-3 status (Fernet is NOT FIPS-validated as a primitive — `cryptography.hazmat` would be required for FIPS deployments).

- [x] CHK016 Are envelope-encryption / per-tenant-key requirements specified for multi-tenant deployments?
  [ACCEPTED]. FR-021 explicitly defers envelope encryption to Phase 2+. Trigger documented.

## Audit Trail Integrity

- [x] CHK017 Is audit-log tamper-evidence specified (cryptographic chaining, hash-tree, signed entries)?
  [GAP]. FR-008 says "append-only via repository interface" but no integrity guarantee against direct-DB tampering. Cross-row chaining was deferred per security audit CHK012.

- [x] CHK018 Is the FR-022 acceptance ("DBA access bypasses both layers; risk accepted residual") cross-referenced to a compensating control (e.g. database access logging, separation of duties)?
  [GAP]. Risk acknowledged; no compensating control named.

- [x] CHK019 Are administrative actions (FR-008 admin_audit_log) categorized so compliance reviewers can filter by action type?
  [PARTIAL]. `action` is a free-text TEXT column. Categorization (high-risk, normal, low-risk) is unspecified.

- [x] CHK020 Is the `before_value` / `after_value` capture (US4 AC4) mandated to redact sensitive fields (e.g. don't log the plaintext API key during a participant.api_key change)?
  [GAP]. Real risk: an admin action that changes a participant's encrypted key could leak plaintext into the audit log if the call site isn't careful. No spec safeguard.

## Retention & Disposal

- [x] CHK021 Are retention periods specified for each table (messages, routing_log, usage_log, convergence_log, admin_audit_log)?
  [PARTIAL]. Only admin_audit_log has FR-019 retention. The others grow indefinitely with no spec policy.

- [x] CHK022 Is secure-disposal specified for storage media (cloud-snapshot encryption, decommissioning)?
  [GAP]. Operator concern but compliance frameworks expect a policy reference.

- [x] CHK023 Is backup retention bounded?
  [GAP]. PostgreSQL backups are operator-managed; SAR / erasure compliance must include backup purge.

## Access Controls

- [x] CHK024 Is the principle-of-least-privilege role separation (FR-022 sacp_app role grants INSERT+SELECT only on logs) actually enforced in Phase 1?
  [DRIFT]. FR-022 says: "the `sacp_app` SQL role is intended to enforce append-only at the database layer in a future deployment hardening pass; in Phase 1 the orchestrator connects with a single role that has DELETE permission." So append-only enforcement is application-layer only. Compliance reviewers will see this as a residual risk.

- [x] CHK025 Are facilitator vs. participant access controls codified at the data layer (not just application layer)?
  [GAP]. Row-level security on PostgreSQL is unused. All access goes through application-layer authz.

- [x] CHK026 Is separation of duties between facilitator and DBA defined?
  [GAP].

## Logging & Monitoring

- [x] CHK027 Is the log-scrubbing dependency (007 §FR-012) cross-referenced as a compliance control?
  [PASS]. FR-020 cross-refs 007 §FR-012 as the confidentiality control for unencrypted message content. Worth elevating: this is a primary compliance control because most sensitive data flows through logs.

- [x] CHK028 Are security incident detection / notification requirements specified (GDPR Art. 33 72-hour notification)?
  [GAP]. Spec is silent on incident response.

- [x] CHK029 Is the security_events table (007 §FR-015) cross-referenced as the compliance-grade incident record?
  [GAP]. Could be — would need an explicit compliance-mapping note.

## Pseudonymization & Minimization

- [x] CHK030 Is data minimization (GDPR Art. 5(c)) enforced — does the system collect only what's necessary?
  [PARTIAL]. The data model is purposeful (no advertising, no behavioral profiling). But `bound_ip` (002 §FR-013) is collected as a security control and could be considered excessive depending on jurisdiction.

## Notes

- 30 items audited. The spec is honest about Phase 1 limits (FR-020, FR-021, FR-022) but doesn't map any limit to a named regulatory regime, leaving compliance posture implicit.
- Highest-leverage findings to convert into spec amendments:
  - CHK001 (name target regime — single sentence; sets the bar for everything else).
  - CHK006 (frame FR-011 vs. FR-019 as a documented Art. 17 compromise with stated lawful basis — defends operators in DPIA).
  - CHK007 (specify a purge enforcer for `SACP_AUDIT_RETENTION_DAYS` — currently advisory, not enforcing).
  - CHK020 (explicit redaction requirement on `before_value` / `after_value` for sensitive-field actions).
  - CHK008 / CHK009 (codify the participant-departure de-identification path or explicitly accept that authored messages are not erasable).
- Lower-priority but useful:
  - CHK015 (FIPS 140-3 status of Fernet — relevant for federal customers; could move to a Phase 3 cryptography swap).
  - CHK024 (move FR-022's "future deployment hardening" out of intent and into a tracked Phase 3 task).
  - CHK010 / CHK011 (SAR self-service path + bounded response window).
- Sister checklists `requirements.md` and `security.md` (closed 2026-04-29). This compliance pass is the Tier 3 follow-up identified in `speckit_checklist_queue.md`. Cross-ref: 010 §debug-export is the operator-side data-export tool; SAR equivalent is missing.
