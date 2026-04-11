# Data Model: Core Data Model

**Feature**: 001-core-data-model
**Source**: sacp-design.md §4.1, sacp-data-security-policy.md, constitution §6-7

## Entity Overview

13 entities organized in 5 groups:

| Group | Entities | Mutability |
|-------|----------|------------|
| Session management | Session, Participant | Mutable (lifecycle transitions) |
| Conversation | Branch, Message | Branch: mutable status; Message: **immutable** |
| Operational logs | RoutingLog, UsageLog, ConvergenceLog, AdminAuditLog | **Append-only** |
| Human-AI coordination | InterruptQueue, ReviewGateDraft | Mutable (delivery/resolution tracking) |
| Participation | Invite, Proposal, Vote | Invite: mutable (use count); Proposal: mutable (status); Vote: **immutable** |

## Entity Definitions

### Session

Root entity. All other entities reference a session.

| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| id | TEXT | PK | UUID or short ID |
| name | TEXT | NOT NULL | Human-readable |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | |
| status | TEXT | NOT NULL, DEFAULT 'active' | active, paused, archived, deleted |
| current_turn | INTEGER | NOT NULL, DEFAULT 0 | Latest turn counter |
| last_summary_turn | INTEGER | NOT NULL, DEFAULT 0 | Most recent checkpoint |
| facilitator_id | TEXT | FK → participants.id | Session admin |
| auto_approve | BOOLEAN | DEFAULT FALSE | Auto-approve new participants |
| auto_archive_days | INTEGER | NULLABLE | null = never |
| auto_delete_days | INTEGER | NULLABLE | null = never |
| parent_session_id | TEXT | NULLABLE | Non-null for forked sessions |
| cadence_preset | TEXT | DEFAULT 'cruise' | sprint, cruise, idle |
| complexity_classifier_mode | TEXT | DEFAULT 'pattern' | pattern, embedding, model_call |
| min_model_tier | TEXT | DEFAULT 'low' | low, mid, high |
| acceptance_mode | TEXT | DEFAULT 'unanimous' | unanimous, majority, facilitator |

**Lifecycle**: active → paused → active (resume) | active/paused → archived | any → deleted

**Bootstrap**: Creating a session MUST atomically create a 'main' Branch.

---

### Participant

A collaborator (human + AI pair) within a session.

| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| id | TEXT | PK | |
| session_id | TEXT | FK → sessions.id, NOT NULL | |
| display_name | TEXT | NOT NULL | |
| role | TEXT | DEFAULT 'pending' | facilitator, participant, pending |
| provider | TEXT | NOT NULL | anthropic, openai, ollama, custom |
| model | TEXT | NOT NULL | e.g., claude-sonnet-4-20250514 |
| model_tier | TEXT | NOT NULL | high, mid, low |
| prompt_tier | TEXT | DEFAULT 'mid' | low, mid, high, max |
| model_family | TEXT | NOT NULL | claude, gpt, llama, mistral, qwen |
| context_window | INTEGER | NOT NULL | Tokens |
| supports_tools | BOOLEAN | DEFAULT TRUE | |
| supports_streaming | BOOLEAN | DEFAULT TRUE | |
| domain_tags | TEXT | NOT NULL, DEFAULT '[]' | JSON array |
| routing_preference | TEXT | DEFAULT 'always' | 8 modes (see Types) |
| observer_interval | INTEGER | DEFAULT 10 | Turns between reads |
| burst_interval | INTEGER | DEFAULT 20 | Turns before burst |
| review_gate_timeout | INTEGER | DEFAULT 600 | Seconds |
| turns_since_last_burst | INTEGER | DEFAULT 0 | Counter |
| turn_timeout_seconds | INTEGER | DEFAULT 60 | Max response wait |
| consecutive_timeouts | INTEGER | DEFAULT 0 | Circuit breaker |
| status | TEXT | DEFAULT 'active' | active, paused, offline, error |
| budget_hourly | REAL | NULLABLE | USD, null = unlimited |
| budget_daily | REAL | NULLABLE | USD, null = unlimited |
| max_tokens_per_turn | INTEGER | NULLABLE | null = model default |
| cost_per_input_token | REAL | NULLABLE | null = LiteLLM lookup |
| cost_per_output_token | REAL | NULLABLE | null = LiteLLM lookup |
| system_prompt | TEXT | NOT NULL, DEFAULT '' | Custom instructions |
| api_endpoint | TEXT | NULLABLE | Provider URL |
| api_key_encrypted | TEXT | NULLABLE | Fernet-encrypted; null = local proxy |
| auth_token_hash | TEXT | NULLABLE | bcrypt hash |
| last_seen | TIMESTAMP | NULLABLE | |
| invited_by | TEXT | FK → participants.id, NULLABLE | Self-referential |
| approved_at | TIMESTAMP | NULLABLE | |

**Departure**: api_key_encrypted overwritten (not nulled), auth_token_hash invalidated, status → 'offline'. Messages retained.

---

### Branch

Conversation thread within a session. 'main' required; additional for Phase 3.

| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| id | TEXT | PK | 'main' for primary |
| session_id | TEXT | FK → sessions.id, NOT NULL | |
| parent_branch_id | TEXT | FK → branches.id, NULLABLE | null for main |
| branch_point_turn | INTEGER | NOT NULL | Turn where divergence occurs |
| name | TEXT | NOT NULL | 'main' or label |
| status | TEXT | DEFAULT 'active' | active, abandoned |
| created_by | TEXT | FK → participants.id, NOT NULL | |
| created_at | TIMESTAMP | DEFAULT NOW() | |

---

### Message (IMMUTABLE)

The conversation transcript. Never updated or deleted during normal operation.

| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| turn_number | INTEGER | PK (composite) | Sequential per session+branch |
| session_id | TEXT | PK (composite), FK → sessions.id | |
| branch_id | TEXT | PK (composite), FK → branches.id, DEFAULT 'main' | |
| parent_turn | INTEGER | NULLABLE | Tree parent for branching |
| speaker_id | TEXT | FK → participants.id | Or system ID |
| speaker_type | TEXT | NOT NULL | ai, human, system, summary |
| delegated_from | TEXT | FK → participants.id, NULLABLE | |
| complexity_score | TEXT | NOT NULL | low, high |
| content | TEXT | NOT NULL | Full message text |
| token_count | INTEGER | NOT NULL | |
| cost_usd | REAL | NULLABLE | |
| created_at | TIMESTAMP | DEFAULT NOW() | |
| summary_epoch | INTEGER | NULLABLE | Summarization cycle |

**Composite PK**: (turn_number, session_id, branch_id)
**Immutability**: No UPDATE or DELETE via application role.

---

### RoutingLog (APPEND-ONLY)

| Field | Type | Constraint |
|-------|------|-----------|
| id | SERIAL | PK |
| session_id | TEXT | FK → sessions.id |
| turn_number | INTEGER | NOT NULL |
| intended_participant | TEXT | FK → participants.id |
| actual_participant | TEXT | FK → participants.id |
| routing_action | TEXT | NOT NULL (11 enum values) |
| complexity_score | TEXT | NOT NULL |
| domain_match | BOOLEAN | NOT NULL |
| reason | TEXT | NOT NULL |
| timestamp | TIMESTAMP | DEFAULT NOW() |

---

### UsageLog (APPEND-ONLY)

| Field | Type | Constraint |
|-------|------|-----------|
| id | SERIAL | PK |
| participant_id | TEXT | FK → participants.id |
| turn_number | INTEGER | NOT NULL |
| input_tokens | INTEGER | NOT NULL |
| output_tokens | INTEGER | NOT NULL |
| cost_usd | REAL | NOT NULL |
| timestamp | TIMESTAMP | DEFAULT NOW() |

---

### ConvergenceLog (APPEND-ONLY)

| Field | Type | Constraint |
|-------|------|-----------|
| turn_number | INTEGER | PK |
| session_id | TEXT | FK → sessions.id |
| embedding | BYTEA | NOT NULL |
| similarity_score | REAL | NOT NULL |
| divergence_prompted | BOOLEAN | DEFAULT FALSE |
| escalated_to_human | BOOLEAN | DEFAULT FALSE |

---

### AdminAuditLog (APPEND-ONLY)

| Field | Type | Constraint |
|-------|------|-----------|
| id | SERIAL | PK |
| session_id | TEXT | FK → sessions.id |
| facilitator_id | TEXT | FK → participants.id |
| action | TEXT | NOT NULL |
| target_id | TEXT | NOT NULL |
| previous_value | TEXT | NULLABLE |
| new_value | TEXT | NULLABLE |
| timestamp | TIMESTAMP | DEFAULT NOW() |

**Survives session deletion**: The admin audit log entry recording a deletion is preserved.

---

### InterruptQueue

| Field | Type | Constraint |
|-------|------|-----------|
| id | SERIAL | PK |
| session_id | TEXT | FK → sessions.id |
| participant_id | TEXT | FK → participants.id |
| content | TEXT | NOT NULL |
| priority | INTEGER | DEFAULT 1 (1=normal, 2=high) |
| status | TEXT | DEFAULT 'pending' |
| created_at | TIMESTAMP | DEFAULT NOW() |
| delivered_at | TIMESTAMP | NULLABLE |

---

### ReviewGateDraft

| Field | Type | Constraint |
|-------|------|-----------|
| id | TEXT | PK |
| session_id | TEXT | FK → sessions.id |
| participant_id | TEXT | FK → participants.id |
| turn_number | INTEGER | NOT NULL |
| draft_content | TEXT | NOT NULL |
| context_summary | TEXT | NOT NULL |
| status | TEXT | DEFAULT 'pending' |
| edited_content | TEXT | NULLABLE |
| created_at | TIMESTAMP | DEFAULT NOW() |
| resolved_at | TIMESTAMP | NULLABLE |

**Status lifecycle**: pending → approved | edited | rejected | timed_out

---

### Invite

| Field | Type | Constraint |
|-------|------|-----------|
| token_hash | TEXT | PK |
| session_id | TEXT | FK → sessions.id |
| created_by | TEXT | FK → participants.id |
| max_uses | INTEGER | DEFAULT 1 |
| uses | INTEGER | DEFAULT 0 |
| expires_at | TIMESTAMP | NULLABLE |
| created_at | TIMESTAMP | DEFAULT NOW() |

---

### Proposal

| Field | Type | Constraint |
|-------|------|-----------|
| id | TEXT | PK |
| session_id | TEXT | FK → sessions.id |
| proposed_by | TEXT | FK → participants.id |
| topic | TEXT | NOT NULL |
| position | TEXT | NOT NULL |
| status | TEXT | DEFAULT 'open' |
| acceptance_mode | TEXT | NOT NULL |
| expires_at | TIMESTAMP | NULLABLE |
| resolved_at | TIMESTAMP | NULLABLE |
| created_at | TIMESTAMP | DEFAULT NOW() |

---

### Vote (IMMUTABLE per composite PK)

| Field | Type | Constraint |
|-------|------|-----------|
| proposal_id | TEXT | PK (composite), FK → proposals.id |
| participant_id | TEXT | PK (composite), FK → participants.id |
| vote | TEXT | NOT NULL (accept, reject, modify) |
| comment | TEXT | NULLABLE |
| created_at | TIMESTAMP | DEFAULT NOW() |

---

## Relationships (ERD Summary)

```text
sessions ──1:N──→ participants
sessions ──1:N──→ branches
sessions ──1:1──→ participants (facilitator_id)
branches ──1:N──→ messages
participants ──1:N──→ messages (speaker_id)
participants ──1:N──→ routing_log
participants ──1:N──→ usage_log
sessions ──1:N──→ convergence_log
sessions ──1:N──→ admin_audit_log
sessions ──1:N──→ interrupt_queue
sessions ──1:N──→ review_gate_drafts
sessions ──1:N──→ invites
sessions ──1:N──→ proposals
proposals ──1:N──→ votes
participants ──0:1──→ participants (invited_by, self-ref)
branches ──0:1──→ branches (parent_branch_id, self-ref)
```

## Indexes (Hot-Path Performance)

| Table | Index | Purpose |
|-------|-------|---------|
| messages | (session_id, branch_id, turn_number DESC) | Fetch recent N turns |
| interrupt_queue | (session_id, status, priority DESC, created_at) | Check pending interjections |
| routing_log | (session_id, turn_number) | Routing history lookup |
| usage_log | (participant_id, timestamp) | Budget enforcement queries |
| participants | (session_id, status) | Active participant lookup |
| invites | (session_id) | Invite listing per session |
| proposals | (session_id, status) | Open proposal lookup |
| review_gate_drafts | (session_id, status) | Pending draft lookup |

## Database Roles

```sql
-- Application role (normal operations)
CREATE ROLE sacp_app WITH LOGIN;
-- Full CRUD on mutable tables
GRANT SELECT, INSERT, UPDATE, DELETE
  ON sessions, participants, branches,
     interrupt_queue, review_gate_drafts,
     invites, proposals
  TO sacp_app;
-- Immutable: INSERT + SELECT only
GRANT SELECT, INSERT
  ON messages, routing_log, usage_log,
     convergence_log, admin_audit_log, votes
  TO sacp_app;

-- Cleanup role (session deletion only)
CREATE ROLE sacp_cleanup WITH LOGIN;
GRANT DELETE ON ALL TABLES IN SCHEMA public
  TO sacp_cleanup;
```

## Data Classification Mapping

| Tier | Fields | Protection |
|------|--------|-----------|
| Tier 1 (Secrets) | api_key_encrypted, auth_token_hash, token_hash | Fernet / bcrypt, never logged |
| Tier 2 (Sensitive) | budget_*, cost_*, usage_log, routing_log | DB role + volume encryption |
| Tier 3 (Content) | messages.content, proposals, convergence_log | DB role + volume encryption |
