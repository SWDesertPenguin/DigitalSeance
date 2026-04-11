# SACP Data Security Policy

Version: 1.0
Date: 2026-04-11
Parent: sacp-constitution.md §7

This document is a supporting policy referenced by the SACP constitution. It defines the data classification, isolation boundaries, retention procedures, key management lifecycle, export access rules, log integrity requirements, and shared data model for the SACP orchestrator. Implementation details for the security mechanisms described here live in `sacp-design.md` (§7.1–7.6) and `AI_attack_surface_analysis_for_SACP_orchestrator.md`.

---

## 1. Data-at-Rest Classification

The orchestrator classifies stored data into three sensitivity tiers, each with its own protection requirement.

### Tier 1 — Secrets (application-layer encryption required)

API keys are encrypted with Fernet (symmetric, AES-128-CBC with HMAC-SHA256) before storage. The orchestrator never writes a plaintext API key to the database, to disk, or to any log. Decryption happens in memory at the moment of provider dispatch, and the plaintext is discarded immediately after use — it is not cached, not held in a class attribute, not passed to any function beyond the HTTP client call. Fernet decrypt operations are offloaded from the async event loop to prevent blocking.

Auth tokens are stored as bcrypt hashes, never in reversible form.

Phase 1 uses a single Fernet key for all participants. Phase 2+ should migrate to envelope encryption — each participant's API key encrypted with a unique Data Encryption Key (DEK), each DEK encrypted with a Key Encryption Key (KEK) stored separately. This limits blast radius: compromising a single DEK exposes one participant's key, not all of them.

### Tier 2 — Sensitive metadata (database access control + volume encryption)

Participant configuration (model choice, routing mode, domain tags, budget caps, prompt tier), usage logs (per-turn token counts, cost), and routing decisions fall into this tier. Protected by PostgreSQL role-based access control — the application connects with a dedicated database role that has the minimum required privileges. The PostgreSQL data directory must be on an encrypted volume (LUKS, dm-crypt, ZFS encryption, or equivalent). This is a deployment requirement, not an application-layer concern, but the policy mandates it.

### Tier 3 — Conversation content (database access control + volume encryption)

Messages, summarization checkpoints, convergence logs, and review-gate drafts are stored in PostgreSQL and protected by the same volume encryption and role-based access as tier 2. Application-layer encryption of conversation content is not required in Phase 1 because all participants in a session have read access to the full transcript by design. If a future phase introduces per-participant content visibility controls, this tier would need to be re-evaluated.

---

## 2. Data-in-Transit Encryption

All data paths that cross a network boundary are encrypted with TLS 1.2 or higher (TLS 1.3 preferred). SSLv3, TLS 1.0, and TLS 1.1 are disabled. Cipher suites are restricted to AES-256-GCM and ChaCha20-Poly1305.

### Five network paths

**Participant ↔ Orchestrator.** MCP SSE (port 8750) and Web UI (port 8751) served over TLS. Termination method (reverse proxy, application-level, tunnel) is deployment-dependent, but cleartext connections are not acceptable. HSTS headers set when served over HTTPS. Certificates must be valid and not self-signed in production (self-signed acceptable for local dev and LAN-only). (Implementation options: design doc §7.4)

**Orchestrator ↔ AI Provider.** All LiteLLM calls go over HTTPS. Provider SDKs enforce this by default — must not be overridden. The orchestrator validates certificates and rejects invalid or expired ones. Local models on the same host or Docker network don't require TLS. Local models on a different LAN machine require TLS or an encrypted tunnel.

**Orchestrator ↔ PostgreSQL.** Same Docker Compose stack = Docker bridge network = trusted, TLS not required. Separate host = TLS required (`ssl='require'` or `ssl='verify-full'` in asyncpg connection).

**Orchestrator ↔ External MCP servers.** Same-host localhost = no encryption needed. Cross-network = TLS required. The orchestrator's MCP client configuration supports a `tls_required` flag per external server.

**Remote participant access.** The orchestrator should not be exposed on a public IP. Remote participants use an encrypted tunnel or VPN (WireGuard, Tailscale, SSH tunnel, cloud tunnel — deployer's choice). SACP requires encrypted and authenticated transport but does not prescribe a product. LAN-only deployments don't need the tunnel layer but TLS on the orchestrator is still recommended.

---

## 3. Key Management Lifecycle

### Fernet key deployment options (increasing security)

**Environment variable (default).** `SACP_ENCRYPTION_KEY` in Docker Compose `.env`. The `.env` file excluded from version control, permissions `chmod 0600`. Appropriate for single-operator home server.

**Docker secret (hardened).** Mounted read-only at `/run/secrets/encryption_key`. Doesn't appear in `docker inspect` or process environment. Recommended for shared-host deployments.

**External secrets manager (enterprise).** Retrieved at startup from Vault, AWS Secrets Manager, Azure Key Vault, or equivalent. Adds runtime dependency but provides centralized management, audit logging, and automatic rotation.

### First-run behavior

If no key is provided at first startup, the orchestrator generates one (`Fernet.generate_key()`), writes it to a configurable path (default `./sacp_encryption.key`), and logs a warning. On subsequent startups, the orchestrator refuses to start if no key is provided and no key file exists — preventing silent data loss from unrecoverable API key encryption.

### Rotation

The `sacp-rotate-key` CLI utility reads the old key, decrypts all `api_key_encrypted` values, re-encrypts with the new key, and updates the database in a single transaction. The deployer swaps the environment variable or secret and restarts. The old key is retained temporarily until rotation is verified, then destroyed.

### Compromise response

If a Fernet key is suspected compromised: generate new key → re-encrypt all API keys via `sacp-rotate-key` → notify all participants to rotate their keys at their providers → revoke all auth tokens (forcing re-authentication). This procedure must be documented and executable.

### Auth token lifecycle

Static tokens (Phase 1) have configurable expiry (default 30 days). The facilitator rotates tokens via `rotate_token` MCP tool. Expired and revoked tokens are rejected immediately. Token hashes of expired/revoked tokens are retained for audit but marked inactive.

### API key updates

Participants update their key via `update_api_key` without re-registering. The orchestrator validates the new key with a test call to the provider. On success, old ciphertext is overwritten (not soft-deleted). On failure, old key remains active. There is no API key history.

---

## 4. Participant Data Isolation

SACP is multi-tenant within a session. Isolation boundaries are enforced at the application layer — a compromised MCP tool call must not extract another participant's secrets.

### Shared (visible to all session participants)

Conversation messages, turn metadata (author, timestamp, model family), routing log entries, convergence log entries, summarization checkpoints, proposals and votes, shared project files/artifacts (Phase 2+), online/offline status, display name, model choice, model family, domain tags, routing preference, role.

### Private (visible only to the owning participant and orchestrator internals)

API keys (encrypted, never in any API response or log), custom system prompt content, exact per-turn cost breakdowns (others see aggregate budget usage percentage only), auth tokens, private annotations (stored client-side, never transmitted).

### Facilitator-visible

All shared fields, plus exact spend for all participants, budget thresholds, approval/rejection history, admin audit log.

### Enforcement

Every MCP tool and API endpoint must filter responses based on the caller's identity. A `get_status` call from Participant A must not return Participant B's API key, system prompt, or exact spend. This filtering is the application's responsibility, not the client's.

---

## 5. Conversation Transparency and Access

### Immutable conversation history

Every message is persisted with full metadata: author (participant ID, human/AI), timestamp, turn number, branch ID, parent turn, complexity score, delegation source, active routing mode. The orchestrator appends to history — it never mutates it. No message is silently dropped, edited, or rewritten.

Participants can retrieve the full history for any session they are or were a member of. Departure does not revoke access to history that existed at departure time. Post-departure history is not accessible unless the participant rejoins. The facilitator can retrieve full history but cannot edit or delete individual messages.

### Four operational log categories

**Routing log** — every turn-routing decision: participant selected, routing mode applied, skip reason (timeout, budget, filter, circuit breaker), complexity classification, domain match, response latency.

**Convergence log** — embedding similarity, lexical overlap metrics, threshold comparisons, actions taken (divergence prompt, pause, escalation).

**Usage log** — per-turn token counts (input/output), cost, model used, cumulative totals. Participants see their own detail. Others see aggregate usage and budget utilization percentage. Facilitator sees exact spend for all.

**Admin audit log** — facilitator actions: approvals/rejections, token revocations, config changes (with previous/new values), archival, removals, facilitator transfers, proposal overrides, exports, security flag responses. Visible to facilitator only in Phase 1. Phase 2 may expose a participant-facing subset.

### Log integrity

Operational logs are append-only. The application's database role has INSERT and SELECT only on log tables — no UPDATE, no DELETE. Session deletion (§6) is the only operation removing log entries, executed atomically via a privileged database role used only for that operation.

### Export

Three formats: markdown (human-readable transcript), JSON (structured data with metadata, logs, proposals, requesting participant's usage), Vaire bulk import (decision summaries for shared memory). Export excludes other participants' detailed usage, API keys, system prompt content, and admin audit log. Available via MCP tool (`export_session`) in Phase 1; Web UI download in Phase 2.

---

## 6. Data Retention and Disposal

When data is deleted, it is deleted — not soft-deleted, not marked inactive, not orphaned.

### Participant departure

API key ciphertext immediately purged (overwritten, not nulled). Auth token invalidated. Active MCP and WebSocket connections closed. Messages remain in history (removing them would break the conversation tree). Participant record marked inactive, retained for referential integrity.

### Session deletion

All associated data deleted: messages, participants (including inactive), routing logs, convergence logs, usage logs, review-gate drafts, interrupt queue entries, proposals, summarization checkpoints, shared files/artifacts. Exception: the admin audit log entry recording the deletion itself is retained. Session deletion is irreversible; the facilitator must confirm explicitly.

### Automatic lifecycle

Sessions support configurable auto-archive (after N days inactive, null = never) and auto-delete (archived sessions purged after N days, null = never). A background cleanup job runs daily. Auto-archive stops the loop and makes the session read-only. Auto-delete triggers the full session deletion procedure.

### Database backups

Backups contain all data including Fernet-encrypted API keys. Docker volume snapshots require encrypted host storage (LUKS, ZFS encryption, or equivalent). Logical backups (`pg_dump`) must be encrypted with GPG or age before storage. Backup encryption keys are managed separately from the Fernet key. Backup retention policy is a deployment concern but must be documented in the deployment guide.

---

## 7. Shared Project Data

### Phase 1 scope

No artifact store. Shared data limited to inline text, code blocks in messages, and structured proposals. External file sharing (drives, repos, paste services) referenced by URL. This is a known limitation, not an oversight — the transcript is not an artifact store.

### Phase 2–3: Artifact store

Session-scoped blob key-value store. Each artifact has an owner, MIME type, size, and timestamp. All session participants can read. Only owner and facilitator can delete. Artifacts referenced by ID in conversation, not embedded inline. Large artifacts get metadata stubs in context, not full content. Subject to session deletion and retention rules. Departed participants' artifacts remain (shared data, not personal).

### Security constraints

Uploaded artifacts are untrusted. MIME type validated against file content. Per-artifact size limit and per-session storage quota enforced. No server-side execution or rendering. Stored as opaque blobs on an encrypted volume consistent with tier 2/3 data-at-rest requirements. Not application-layer encrypted (all session participants have read access by design).
