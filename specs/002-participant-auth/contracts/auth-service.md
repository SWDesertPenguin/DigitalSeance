# Auth Service Interface Contract

**Feature**: 002-participant-auth
**Pattern**: Service class composing ParticipantRepository + LogRepository

## AuthService

```
authenticate(token, client_ip) → Participant
  - Hash token with bcrypt, compare against all participant hashes
  - Check token_expires_at (reject if expired)
  - Check bound_ip (reject if mismatch, bind if first auth)
  - Returns authenticated Participant or raises

approve_participant(facilitator_id, participant_id) → Participant
  - Guard: caller must be facilitator
  - Guard: target must be pending
  - Updates role → 'participant', sets approved_at
  - Logs to admin_audit_log

reject_participant(facilitator_id, participant_id, reason?) → None
  - Guard: caller must be facilitator
  - Guard: target must be pending
  - Removes participant record
  - Logs rejection with reason to admin_audit_log

rotate_token(participant_id) → str
  - Generates new token (secrets.token_urlsafe)
  - Hashes with bcrypt, updates auth_token_hash
  - Resets token_expires_at to now + configured period
  - Clears bound_ip (allows rebinding)
  - Returns new plaintext token (shown once)

revoke_token(facilitator_id, participant_id) → None
  - Guard: caller must be facilitator
  - Generates random hash (invalidates old token)
  - Clears bound_ip
  - Logs to admin_audit_log

remove_participant(facilitator_id, participant_id, reason?) → None
  - Guard: caller must be facilitator
  - Guard: facilitator cannot remove themselves
  - Calls existing depart_participant (key overwrite + token invalidation)
  - Logs to admin_audit_log with reason

transfer_facilitator(facilitator_id, target_id) → None
  - Guard: caller must be current facilitator
  - Guard: target must be active participant (not pending)
  - Updates target role → 'facilitator'
  - Updates caller role → 'participant'
  - Updates session.facilitator_id
  - Logs to admin_audit_log
```

## Guard Functions

```
require_facilitator(session_id, caller_id) → None
  - Raises NotFacilitatorError if caller is not the session facilitator

require_active(participant_id) → None
  - Raises ValueError if participant status != 'active'

require_pending(participant_id) → None
  - Raises ValueError if participant role != 'pending'

require_not_self(caller_id, target_id) → None
  - Raises ValueError if caller_id == target_id
```

## Error Types (additions to errors.py)

```
TokenExpiredError      — token past expiry timestamp
TokenInvalidError      — token hash does not match any participant
AuthRequiredError      — no token provided
NotFacilitatorError    — caller lacks facilitator role
IPBindingMismatchError — token valid but client IP doesn't match bound IP
```
