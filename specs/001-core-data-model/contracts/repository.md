# Repository Interface Contracts

**Feature**: 001-core-data-model
**Pattern**: Repository per entity group, asyncpg pool injected

All repositories accept an `asyncpg.Pool` at construction. All methods are async. All return frozen dataclass instances (never raw Records to callers).

## SessionRepository

```
create_session(name, facilitator_id, config) → Session
  - Atomically creates session + 'main' branch + facilitator participant
  - Returns fully hydrated Session with defaults applied

get_session(session_id) → Session | None

update_status(session_id, new_status) → Session
  - Validates transition: active↔paused, active/paused→archived, any→deleted
  - Raises InvalidTransition on illegal transition

delete_session(session_id) → None
  - Uses elevated role (sacp_cleanup)
  - Atomically removes all associated data EXCEPT admin_audit_log entry
  - Logs deletion to admin_audit_log before removing data

list_sessions(status_filter?) → list[Session]
```

## ParticipantRepository

```
add_participant(session_id, config) → Participant
  - Encrypts api_key before storage
  - Hashes auth_token before storage
  - Sets initial status based on session auto_approve

get_participant(participant_id) → Participant | None
  - api_key_encrypted returned as-is (caller decrypts only at dispatch)

update_participant(participant_id, fields) → Participant
  - Partial update: only provided fields changed
  - api_key re-encrypted if changed

depart_participant(participant_id) → None
  - Overwrites api_key_encrypted with random bytes (not null)
  - Invalidates auth_token_hash
  - Sets status = 'offline'
  - Messages retained

list_participants(session_id, status_filter?) → list[Participant]
```

## MessageRepository

```
append_message(session_id, branch_id, speaker_id, speaker_type,
               content, token_count, cost_usd?, parent_turn?,
               complexity_score, delegated_from?, summary_epoch?)
  → Message
  - Auto-assigns next turn_number for session+branch
  - Rejects if session status != 'active'
  - Uses prepared statement (hot path)

get_recent(session_id, branch_id, limit) → list[Message]
  - Prepared statement
  - Returns most recent N messages in turn order

get_range(session_id, branch_id, start_turn, end_turn) → list[Message]

get_by_speaker(session_id, speaker_id) → list[Message]

get_summaries(session_id, branch_id) → list[Message]
  - Filters speaker_type = 'summary'
```

**No update or delete methods exposed.** Immutability enforced by interface.

## LogRepository

```
# Routing Log
log_routing(session_id, turn_number, intended, actual,
            action, complexity, domain_match, reason) → RoutingLog

get_routing_history(session_id, limit?) → list[RoutingLog]

# Usage Log
log_usage(participant_id, turn_number, input_tokens,
          output_tokens, cost_usd) → UsageLog

get_participant_usage(participant_id, since?) → list[UsageLog]

get_participant_cost(participant_id, period) → float
  - Aggregates cost_usd for budget enforcement

# Convergence Log
log_convergence(turn_number, session_id, embedding,
                similarity_score) → ConvergenceLog

get_convergence_window(session_id, window_size) → list[ConvergenceLog]

# Admin Audit Log
log_admin_action(session_id, facilitator_id, action,
                 target_id, previous_value?, new_value?) → AdminAuditLog

get_audit_log(session_id) → list[AdminAuditLog]
```

**No update or delete methods exposed.** Append-only enforced by interface.

## InterruptRepository

```
enqueue(session_id, participant_id, content, priority?) → InterruptEntry

get_pending(session_id) → list[InterruptEntry]
  - Ordered by priority DESC, created_at ASC
  - Prepared statement (hot path)

mark_delivered(interrupt_id) → InterruptEntry
  - Sets status = 'delivered', delivered_at = NOW()
```

## ReviewGateRepository

```
create_draft(session_id, participant_id, turn_number,
             draft_content, context_summary) → ReviewGateDraft

get_pending(session_id) → list[ReviewGateDraft]

resolve(draft_id, resolution, edited_content?) → ReviewGateDraft
  - resolution: 'approved' | 'edited' | 'rejected' | 'timed_out'
  - Sets resolved_at = NOW()
  - If 'edited': stores edited_content
```

## InviteRepository

```
create_invite(session_id, created_by, max_uses?, expires_at?)
  → (Invite, plaintext_token)
  - Returns both the record (with hash) and the one-time plaintext

redeem_invite(plaintext_token) → Invite
  - Hashes token, looks up, validates use count and expiry
  - Increments uses
  - Raises InviteExpired or InviteExhausted on failure

list_invites(session_id) → list[Invite]
```

## ProposalRepository

```
create_proposal(session_id, proposed_by, topic, position,
                acceptance_mode, expires_at?) → Proposal

cast_vote(proposal_id, participant_id, vote, comment?) → Vote
  - Raises DuplicateVote if already voted

get_votes(proposal_id) → list[Vote]

resolve_proposal(proposal_id, status) → Proposal
  - status: 'accepted' | 'rejected' | 'expired'

get_open_proposals(session_id) → list[Proposal]
```

## Error Types

```
InvalidTransition     — illegal session status transition
DuplicateVote         — participant already voted on proposal
InviteExpired         — invite past expiry timestamp
InviteExhausted       — invite max_uses reached
EncryptionKeyMissing  — SACP_ENCRYPTION_KEY not set (fail-closed)
SessionNotActive      — operation requires active session
```

## Prepared Statements (Hot Path)

These queries run every turn cycle and MUST use asyncpg prepared statements:

1. `fetch_recent_messages` — get last N messages for context assembly
2. `check_pending_interrupts` — check interrupt queue before routing
3. `append_message` — insert new message with auto-incremented turn
4. `log_routing_decision` — insert routing log entry
