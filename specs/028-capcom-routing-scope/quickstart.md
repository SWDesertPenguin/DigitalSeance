# Quickstart: CAPCOM-Like Routing Scope

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Phase**: 1 (Design) | **Date**: 2026-05-14

A step-by-step verification recipe for the CAPCOM routing-scope feature. Drives every Success Criterion (SC-001..SC-015) through an end-to-end scenario.

## Prerequisites

- `SACP_CAPCOM_ENABLED=true` set in the environment
- `SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN=false` (the v1 default — humans publish to `public` by default and explicitly opt into `capcom_only`)
- A running orchestrator instance with the 024 migration applied
- Facilitator credentials for an active session containing one human + four AI participants (one will become CAPCOM; three remain panel)

## Step 1 — Confirm the master switch + endpoint discovery

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/sessions/$SESSION_ID/capcom/assign
# Expected: 401 (unauthenticated) — the route IS mounted because SACP_CAPCOM_ENABLED=true.
```

Now flip the master switch off and restart; the same request should return `404`. Flip it back on for the rest of the recipe.

**Verifies**: SC-012 (master switch unreachable when false).

## Step 2 — Assign a CAPCOM

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/capcom/assign \
  -H "Cookie: sacp_session=<facilitator_cookie>" \
  -H "Content-Type: application/json" \
  -d '{"participant_id": "ai-1"}'
# Expected: 200 with the assigned participant payload
```

Inspect `sessions.capcom_participant_id`:

```sql
SELECT capcom_participant_id FROM sessions WHERE id = '$SESSION_ID';
-- Expected: 'ai-1'
```

Inspect `admin_audit_log`:

```sql
SELECT action, target_participant_id FROM admin_audit_log
WHERE session_id = '$SESSION_ID' ORDER BY timestamp DESC LIMIT 1;
-- Expected: ('capcom_assigned', 'ai-1')
```

Subscribe to the session WebSocket and observe a `capcom_assigned` event arriving within 2s.

**Verifies**: FR-007, FR-021 (master-switch routing), WS event delivery budget.

## Step 3 — Verify single-CAPCOM enforcement (concurrency)

Attempt to assign a second CAPCOM:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/capcom/assign \
  -H "Cookie: sacp_session=<facilitator_cookie>" \
  -H "Content-Type: application/json" \
  -d '{"participant_id": "ai-2"}'
# Expected: 409 (single-CAPCOM-per-session — the unique partial index rejects)
```

**Verifies**: FR-005, SC-006 (single-CAPCOM enforcement at DB layer).

## Step 4 — Drive a CAPCOM-mediated exchange

Inject a human message in `capcom_only` scope:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/messages \
  -H "Cookie: sacp_session=<human_cookie>" \
  -H "Content-Type: application/json" \
  -d '{"content": "Panel: should we proceed with option B?", "visibility": "capcom_only"}'
# Expected: 200 with the new message row
```

Drive a panel AI's next dispatch. Inspect its context:

```bash
curl -sS http://localhost:8000/sessions/$SESSION_ID/debug/export \
  -H "Cookie: sacp_session=<facilitator_cookie>" | \
  jq '.context_by_participant["ai-2"].messages | map(.visibility) | unique'
# Expected: ["public"] — ai-2 (a panel AI) does NOT see the capcom_only message.
```

Drive the CAPCOM AI's dispatch. Inspect its context:

```bash
curl -sS http://localhost:8000/sessions/$SESSION_ID/debug/export \
  -H "Cookie: sacp_session=<facilitator_cookie>" | \
  jq '.context_by_participant["ai-1"].messages | map(.visibility) | unique'
# Expected: ["public", "capcom_only"] — ai-1 (the CAPCOM) sees both scopes.
```

CAPCOM AI emits a `capcom_relay`:

```sql
SELECT kind, visibility FROM messages
WHERE session_id = '$SESSION_ID' AND speaker_id = 'ai-1'
ORDER BY turn_number DESC LIMIT 1;
-- Expected: ('capcom_relay', 'public')
```

Drive a panel AI's dispatch again; assert its context now includes the `capcom_relay`.

**Verifies**: SC-001, SC-002, SC-003, FR-006, FR-012.

## Step 5 — Drive a CAPCOM query + human response

CAPCOM AI emits a `capcom_query`:

```sql
SELECT kind, visibility FROM messages
WHERE session_id = '$SESSION_ID' AND kind = 'capcom_query'
ORDER BY turn_number DESC LIMIT 1;
-- Expected: ('capcom_query', 'capcom_only')
```

Human responds:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/messages \
  -H "Cookie: sacp_session=<human_cookie>" \
  -H "Content-Type: application/json" \
  -d '{"content": "Yes, proceed with B.", "reply_to_query_id": "<query_message_id>"}'
# Expected: 200; the response defaults to visibility='capcom_only' per FR-014
```

Confirm:

```sql
SELECT visibility FROM messages
WHERE session_id = '$SESSION_ID' AND parent_turn IS NOT NULL
ORDER BY turn_number DESC LIMIT 1;
-- Expected: 'capcom_only'
```

Drive a panel AI's dispatch; assert its context does NOT include the human response.

**Verifies**: SC-004, SC-005, FR-013, FR-014.

## Step 6 — Rotate CAPCOM

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/capcom/rotate \
  -H "Cookie: sacp_session=<facilitator_cookie>" \
  -H "Content-Type: application/json" \
  -d '{"new_participant_id": "ai-2"}'
# Expected: 200; transactional swap
```

Confirm:

```sql
SELECT capcom_participant_id FROM sessions WHERE id = '$SESSION_ID';
-- Expected: 'ai-2'

SELECT id, routing_preference FROM participants
WHERE session_id = '$SESSION_ID' AND id IN ('ai-1', 'ai-2');
-- Expected: ai-1 routing_preference reverted; ai-2 routing_preference='capcom'
```

Drive ai-2's dispatch; assert its context contains public history ONLY — none of the prior `capcom_only` exchanges between ai-1 and the human.

**Verifies**: FR-008, FR-010, SC-007.

Inspect the `admin_audit_log`:

```sql
SELECT action, previous_capcom_id, new_capcom_id FROM admin_audit_log
WHERE session_id = '$SESSION_ID' ORDER BY timestamp DESC LIMIT 1;
-- Expected: ('capcom_rotated', 'ai-1', 'ai-2')
```

The prior `capcom_only` messages retain `speaker_id='ai-1'` (no historical attribution rewrite):

```sql
SELECT DISTINCT speaker_id FROM messages
WHERE session_id = '$SESSION_ID' AND visibility = 'capcom_only'
  AND turn_number < <rotation_turn>;
-- Expected: contains 'ai-1' (and 'human-1'); does NOT contain 'ai-2'
```

**Verifies**: FR-010 (no historical-attribution rewrite), INV-5.

## Step 7 — Panel-AI cannot emit `capcom_only` (INV-4)

Manually attempt to write a `capcom_only` message as a panel AI:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/messages \
  -H "Cookie: sacp_session=<ai_3_cookie>" \
  -H "Content-Type: application/json" \
  -d '{"content": "Private to humans", "visibility": "capcom_only"}'
# Expected: 422 with body referencing INV-4 / panel-AI restriction
```

**Verifies**: spec.md Clarifications Session 2026-05-14 Q2 / INV-4.

## Step 8 — Disable CAPCOM

```bash
curl -X DELETE http://localhost:8000/sessions/$SESSION_ID/capcom \
  -H "Cookie: sacp_session=<facilitator_cookie>"
# Expected: 200 with confirmation payload
```

Confirm:

```sql
SELECT capcom_participant_id FROM sessions WHERE id = '$SESSION_ID';
-- Expected: NULL
```

Inject a new human message without specifying visibility:

```bash
curl -X POST http://localhost:8000/sessions/$SESSION_ID/messages \
  -H "Cookie: sacp_session=<human_cookie>" \
  -H "Content-Type: application/json" \
  -d '{"content": "Back to symmetric mode"}'
# Expected: 200; row written with visibility='public'
```

Drive every AI's next dispatch. Assert each context now contains the new public message. Assert each AI's context still EXCLUDES the historical `capcom_only` messages (no retroactive promotion per FR-011).

**Verifies**: FR-009, FR-011, SC-008.

## Step 9 — Departure-without-replacement

Re-assign CAPCOM (ai-2), then remove the participant:

```bash
curl -X DELETE http://localhost:8000/sessions/$SESSION_ID/participants/ai-2 \
  -H "Cookie: sacp_session=<facilitator_cookie>"
# Expected: 200
```

Confirm:

```sql
SELECT capcom_participant_id FROM sessions WHERE id = '$SESSION_ID';
-- Expected: NULL

SELECT action FROM admin_audit_log
WHERE session_id = '$SESSION_ID' ORDER BY timestamp DESC LIMIT 1;
-- Expected: 'capcom_departed_no_replacement'
```

**Verifies**: FR-022, SC-014.

## Step 10 — Two-tier summarizer (FR-018)

Re-assign CAPCOM, drive the session past one summarization checkpoint (typically 10+ turns), then inspect:

```sql
SELECT summary_scope, LENGTH(summary_text) FROM checkpoint_summaries
WHERE session_id = '$SESSION_ID' ORDER BY checkpoint_turn DESC LIMIT 2;
-- Expected: two rows — ('panel', N1) and ('capcom', N2). N2 typically >= N1 (capcom view is larger).
```

Drive a panel AI's dispatch on the next post-checkpoint turn; confirm its context includes the `panel`-scope summary (not the `capcom`-scope summary). Drive the CAPCOM AI's dispatch; confirm its context includes the `capcom`-scope summary.

**Verifies**: FR-018, SC-011.

## Step 11 — Architectural test (FR-019 / SC-009)

```bash
pytest tests/test_028_architectural.py -v
# Expected: PASS — every messages.content read site is in the allowlist with documented justification.
```

Add a synthetic bypass to a file outside the allowlist (e.g., `src/orchestrator/dispatcher.py` with `msg.content` directly), rerun:

```bash
pytest tests/test_028_architectural.py -v
# Expected: FAIL with a structured error naming the offending file:line.
```

Roll back the synthetic bypass.

**Verifies**: FR-019, SC-009.

## Step 12 — Debug-export visibility reflection (FR-024 / SC-015)

```bash
curl -sS http://localhost:8000/sessions/$SESSION_ID/debug/export \
  -H "Cookie: sacp_session=<facilitator_cookie>" > export.json
```

For each participant in `export.json.context_by_participant`:
- If the participant is the CAPCOM, assert the messages list contains both `public` and `capcom_only` visibility values.
- Otherwise, assert the messages list contains only `public` values.

**Verifies**: FR-024, SC-015.

## Negative regression check — pre-feature behavior preserved

Flip the master switch off (`SACP_CAPCOM_ENABLED=false`), restart. Drive a fresh session with one human + four AIs (none assigned as CAPCOM). Inject a human message without specifying visibility. Confirm every AI sees the message (symmetric visibility, identical to pre-feature behavior). Attempt to assign a CAPCOM — receive HTTP 404. Attempt to inject `capcom_only` — receive HTTP 409.

**Verifies**: FR-021 (master-switch gating) + the no-CAPCOM degenerate case from spec User Story 1 Acceptance Scenario 4.
