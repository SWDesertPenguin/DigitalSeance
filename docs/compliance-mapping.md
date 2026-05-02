# SACP Compliance Mapping

This doc aggregates SACP's regulatory traceability: GDPR, NIST (CSF 2.0 / 800-53B / AI 100-2), and EU AI Act mappings. Each entry points to what SACP does to satisfy the requirement.

This is a working compliance crib sheet, not a formal compliance certification. Operators using SACP in regulated environments are responsible for their own compliance posture; this doc gives them a starting map.

---

## 1. GDPR article mapping

| Article | Topic | SACP coverage |
|---|---|---|
| Art. 5(1)(c) | Data minimization | Encrypted-field strip on every WS broadcast; pending-participant snapshot filter limits visibility before approval |
| Art. 6 | Lawful basis | Operator's deployment policy responsibility — SACP does not enumerate grounds. Document in deploy-time policy. |
| Art. 13 | Information to data subject | Operator's UI / consent flow responsibility; SACP's Web UI surfaces participant role + visibility on connect |
| Art. 15 | Subject access request (SAR) | Per-participant export via debug-export tool; operator can dump full session via DB |
| Art. 17 | Right to erasure | Per-participant cascade; per-session cascade via `DELETE FROM sessions`; `admin_audit_log` carve-out per Art. 17(3)(b) |
| Art. 20 | Data portability | JSON export via debug-export tool; machine-readable transcripts |
| Art. 25 | Data protection by design | Secure-by-design principle in the constitution; fail-closed defaults across the security pipeline |
| Art. 28 | Processor relationships | Operator-deployed; sponsor-AI relationship via `participants.invited_by` documents who supplies the third-party API key |
| Art. 30 | Records of processing | `admin_audit_log` survives session deletion; `routing_log`, `usage_log`, `security_events` together form the activity record |
| Art. 32 | Security of processing | Encryption-at-rest via Fernet; IP-binding on tokens; fail-closed pipeline; rate limiting |
| Art. 33 | Breach notification (to authority) | Operator responsibility — SACP surfaces `security_events` and an internal red-team runbook as raw signal |
| Art. 34 | Subject notification | Operator responsibility |
| Art. 44 | International transfer | Operator's deployment topology — SACP is single-region by default; cross-region requires deploy operator's standard contractual clauses |

**Audit-log survival rationale**: `admin_audit_log` deliberately survives session deletion because Art. 17(3)(b) carves out retention "for compliance with a legal obligation" — facilitator action records may be subject to subsequent regulatory review even after the session is purged for the data subject's erasure right.

---

## 2. NIST CSF 2.0 mapping

| Function | Subcategory | SACP coverage |
|---|---|---|
| GOVERN | GV.OC-01 (mission, expectations) | Constitution §1 (Mission), §3 (Sovereignty) |
| GOVERN | GV.RM-01 (risk acceptance) | Constitution §4.9 (secure-by-design); §12 V-series invariants |
| IDENTIFY | ID.AM-02 (assets inventory) | Per-table retention inventory; alembic migration history |
| IDENTIFY | ID.RA-01 (vulnerabilities identified) | Internal AI attack-surface analysis; internal red-team runbook incident catalog |
| PROTECT | PR.AA-01 (identities & creds) | Token issuance, IP binding, rotation; encryption-at-rest for `api_key_encrypted` |
| PROTECT | PR.AA-05 (least-privilege) | Per-role permission matrix; per-event filtering; `audit_entry` facilitator-only fanout |
| PROTECT | PR.DS-01 (data at rest) | Fernet encryption for sensitive participant fields; `SACP_ENCRYPTION_KEY` validation |
| PROTECT | PR.DS-02 (data in transit) | TLS deployment-layer responsibility; WebSocket origin / IP-binding validation |
| PROTECT | PR.IR-01 (config baselines) | Constitution §12 V16 config validation; env-var catalog with ranges |
| DETECT | DE.CM-01 (continuous monitoring) | `routing_log`, `security_events`, `convergence_log` as DB-side observability |
| DETECT | DE.AE-02 (event analysis) | Per-layer findings in `security_events.findings`; `layer_duration_ms` for timing analysis |
| RESPOND | RS.MA-01 (incident response plan) | Operational runbook incident-response section |
| RESPOND | RS.AN-01 (notifications) | `error` WS events + `audit_entry` events for facilitator visibility |
| RECOVER | RC.RP-01 (recovery plan) | Operational runbook backup / restore section |

---

## 3. NIST 800-53B (moderate baseline)

| Control | SACP coverage |
|---|---|
| AC-2 (account management) | Participant lifecycle state machine (pending → active → paused → removed) |
| AC-3 (access enforcement) | Per-role permission matrix; HTTPException 403 surface |
| AC-7 (unsuccessful logon attempts) | Rate limiter on `/tools/*`; circuit breaker on participant authentication failures |
| AU-2 (event logging) | `admin_audit_log`, `security_events`, `routing_log` |
| AU-9 (protection of audit info) | Append-only repository interface (no UPDATE / DELETE methods on the log repository) |
| AU-11 (audit record retention) | `admin_audit_log` survives session deletion |
| CM-2 (baseline configuration) | Env-var catalog + V16 startup validation |
| CM-6 (configuration settings) | Per-var ranges + validators |
| IA-2 (identification & authentication) | Token + IP-binding; encryption-at-rest for tokens |
| IA-5 (authenticator management) | Rotation ceremony rotates without downtime |
| IR-4 (incident handling) | Operational runbook + internal red-team runbook |
| RA-5 (vulnerability monitoring) | OSINT source registry; periodic image scans per Constitution §6.8 |
| SC-8 (transmission confidentiality) | TLS at deploy layer; Fernet at row layer |
| SC-12 (cryptographic key establishment) | Operator-managed `SACP_ENCRYPTION_KEY` per-deployment; rotation ceremony in operational runbook |
| SI-3 (malicious code protection) | Sanitizer / exfiltration / jailbreak layers |
| SI-7 (software & information integrity) | Append-only logs, advisory-lock single-loop invariant |

---

## 4. NIST AI 100-2 (adversarial ML)

| Threat class | SACP coverage |
|---|---|
| Prompt injection (direct) | Sanitizer layer with adversarial-corpus regression coverage |
| Prompt injection (indirect, via tool / RAG) | Out of scope for current threat model; revisit when retrieval lands |
| Data exfiltration | Exfiltration layer with credential / canary / exfil-marker patterns; canary placement |
| Jailbreak / refusal-bypass | Jailbreak detection layer; pattern updates via the documented update workflow |
| Membership inference | Out of scope for current threat model; revisit per Phase 3 review |
| Model evasion (homoglyphs / unicode tricks) | Sanitizer Cyrillic-homoglyph guard (post-incident addition) |
| Output manipulation / convergence collapse | Convergence detector; divergence-prompt injection |
| Untrusted-third-party-AI risk | `participants.invited_by` traces sponsor; sponsor's API key is participant-scoped (no cross-participant leak) |

---

## 5. EU AI Act mapping (where relevant)

SACP is a multi-AI orchestration platform. AI Act applicability depends on the deployer's use case; this section covers articles SACP's design addresses regardless of intended use.

| Article | Topic | SACP coverage |
|---|---|---|
| Art. 10 | Data governance | Per-table retention inventory; per-participant cascade |
| Art. 12 | Record-keeping | `admin_audit_log`, `routing_log`, `usage_log`, `security_events` |
| Art. 13 | Transparency to deployer | This compliance map; the public design doc |
| Art. 14 | Human oversight | Review-gate mechanism; facilitator role |
| Art. 15 | Accuracy, robustness, cybersecurity | Fail-closed pipeline; pattern-list update workflow; internal red-team runbook |
| Art. 17 | Quality management | Speckit workflow; audit follow-through tracking |

---

## 6. Per-spec compliance traceability

| Spec | Compliance themes |
|---|---|
| 001 (foundation) | Art. 17 erasure cascade; Art. 30 records; AU-9 / AU-11 audit-log survival |
| 002 (auth) | Art. 32 encryption-at-rest of tokens; IA-2 / IA-5 |
| 003 (turn loop) | AU-2 (routing_log); SI-7 (advisory-lock single-loop); V14 timing instrumentation |
| 004 (convergence) | Art. 12 record-keeping; AI 100-2 convergence-collapse |
| 005 (summarization) | Art. 5(1)(c) minimization (summarized context) |
| 007 (security pipeline) | AI 100-2 prompt-injection / exfiltration / jailbreak; Art. 14 human oversight (review-gate); SI-3 |
| 008 (canary) | AI 100-2 data exfiltration |
| 009 (rate limiting) | AC-7 unsuccessful-logon throttling |
| 010 (debug export) | Art. 15 SAR; Art. 20 portability |
| 011 (Web UI) | Art. 13 transparency; PR.AA-05 least-privilege; minimization filters |
| 012 (audit fixes) | Art. 25 by-design; CM-2 / CM-6 config validation; AU-2 timing instrumentation |
