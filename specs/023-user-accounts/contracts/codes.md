# Contract: Single-Use Verification + Reset Codes

**Branch**: `023-user-accounts` | **Source**: spec FR-004, FR-014, edge cases, clarify Q4 | **Date**: 2026-05-09

Defines the format, generation, persistence, consumption, TTL, and ScrubFilter rules for the 16-character base32 single-use codes used for email verification, password reset, and email-change verification. Cross-references research.md §3.

---

## Code format

- **Length**: exactly 16 characters.
- **Alphabet**: Crockford base32 — `0123456789ABCDEFGHJKMNPQRSTVWXYZ` (drops visually ambiguous `I`, `L`, `O`, `U`).
- **Entropy**: ~80 bits (16 chars × 5 bits = 80; minus alphabet skew is negligible at this entropy level).
- **Encoding**: case-insensitive on input (the orchestrator normalizes to uppercase before HMAC comparison); Crockford-style ambiguity normalization on input (`I→1`, `L→1`, `O→0`).

---

## Generation

```python
import secrets
from base64 import b32encode

_CROCKFORD_TABLE = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "ABCDEFGHJKMNPQRSTVWXYZ0123",  # standard b32 → Crockford remap
)


def generate_code() -> str:
    """Generate a 16-character Crockford base32 code with ~80 bits of entropy."""
    raw = secrets.token_bytes(10)  # 10 bytes = 80 bits
    encoded = b32encode(raw).decode("ascii").rstrip("=")  # standard b32 → Crockford translate
    return encoded[:16].translate(_CROCKFORD_TABLE)
```

The `secrets.token_bytes(10)` call sources from `os.urandom`; 10 bytes maps to exactly 16 base32 chars before padding. The Crockford translation drops visually ambiguous chars from the output.

---

## Persistence

Codes are NOT persisted as durable rows in a `verification_codes` table. They live only in `admin_audit_log` rows (research.md §3). Two row patterns:

1. **Emit row** (`account_verification_emitted` / `account_password_reset_emitted` / `account_email_change_emitted`):
   - `code_hash`: HMAC-SHA256 of the plaintext code, using `SACP_AUTH_LOOKUP_KEY` (the same secret already used for the participant-token lookup index).
   - `expires_at`: timestamp deadline = emit time + TTL.
   - `account_id`: target account.
   - For email-change codes: `new_email_hash` (the new email this code authorizes the change to).

2. **Consume row** (`*_consumed`):
   - `emit_row_id`: FK-style reference to the matching emit row's id.
   - `consumed_at`: when the consumption succeeded.

A code is considered consumed iff a matching `*_consumed` row exists for its emit row's id. Re-submission of the same plaintext is rejected by checking for the consume row.

### Plaintext storage in `_dev_plaintext` (noop transport only)

The `NoopEmailTransport` audit row (`account_email_noop_emitted`) carries a `_dev_plaintext` field containing the literal plaintext code (per `contracts/email-transport.md`). This field exists ONLY when the noop adapter is selected — the cross-condition WARN at startup flags this combination as production-unsafe. The ScrubFilter MUST treat `_dev_plaintext` as scrub-on-egress: the field appears in the audit-log INSERT, but is scrubbed from any log line that reads back from the audit log.

---

## TTLs

Per spec FR-004 + clarify Q4:

| Purpose | TTL |
|---|---|
| Email verification (account creation) | 24 hours |
| Password reset | 30 minutes |
| Email change verification | 24 hours |

TTL enforcement: at consumption time, the orchestrator reads the matching emit row, compares `expires_at` to `now()`, and rejects if `now() > expires_at` with a generic `invalid_or_expired_code` error (no info leak about which condition failed — wrong code vs. expired code vs. wrong account_id).

---

## Consumption semantics

### Single-use enforcement

A code is consumed at most once. Re-submission of the same plaintext after consumption is rejected (the `_consumed` row exists for the emit row's id).

### Generic error responses

All code-related failures return HTTP 400 with body `{"error": "invalid_or_expired_code"}`. The application MUST NOT distinguish:

- Wrong code (HMAC mismatch).
- Expired code (`now() > expires_at`).
- Already-consumed code (`_consumed` row exists).
- Wrong account_id (the code does not belong to the submitted account).

This is a defense-in-depth measure mirroring SC-005's timing-attack-resistance contract — the failure path consumes constant time regardless of the underlying condition.

### Account-id scope

Codes are scoped to `account_id` — the consume request MUST include the target account_id and the orchestrator MUST verify the emit row belongs to that account. Cross-account code submission is rejected.

---

## Pre-auth rate-limiter integration

Code consumption endpoints (`/tools/account/verify`, `/tools/account/email/verify`, the future `/tools/account/password/reset`) are subject to the same pre-auth per-IP rate limiter as `/login` and `/create-account` (FR-015). Each consume attempt counts toward the per-IP threshold; limit exceedance returns HTTP 429 + `Retry-After`.

Reset attempts MUST count toward the FR-015 limiter per clarify Q4 — preventing reset-code-grinding attacks.

---

## ScrubFilter coverage (FR-014, SC-012)

The following MUST be scrubbed from every log line that is NOT the audit-log INSERT itself:

1. **Plaintext codes** — pattern match `[0-9A-HJKMNP-TV-Z]{16}` (Crockford base32 character class). The pattern is sufficiently specific that false positives on natural English are negligible at 16-char length.
2. **`_dev_plaintext` field content** — when the noop adapter's audit row is read back into application memory, the field is scrubbed before any log-emission downstream.
3. **Code-bearing email body content** — already covered by the email-transport ScrubFilter rule (`contracts/email-transport.md`), since codes are embedded in email bodies.

The HMAC hash form is safe to log (it's already non-recoverable).

---

## Test obligations

- `test_023_account_create.py`:
  - Generated code is exactly 16 chars, in the Crockford alphabet, with ~80 bits of entropy (Shannon estimate over a sample).
  - Emit row's `code_hash` matches HMAC-SHA256 of the plaintext (computed locally).
- `test_023_account_create.py`:
  - Verification within TTL succeeds; consume row is written; account flips to active.
  - Verification AFTER TTL fails with `invalid_or_expired_code`.
  - Re-submission of the same code fails with `invalid_or_expired_code` (the consume row exists).
  - Submission of a code belonging to a different account fails with `invalid_or_expired_code`.
- `test_023_email_change.py`:
  - 24h TTL applies; same shape as verification.
- `test_023_password_change.py` (when reset endpoint lands): 30-min TTL applies; reset attempts count toward FR-015 limiter.
- `test_023_scrub_filter.py`:
  - Plaintext codes do NOT appear in any log line outside the audit-log INSERT.
  - `_dev_plaintext` content is scrubbed from any log line that reads back from the audit log.
  - Cross-spec test: email-body content containing the code is scrubbed by the email-transport ScrubFilter rule (delegated to `contracts/email-transport.md`'s test obligations).
