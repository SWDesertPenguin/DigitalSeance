# Contract: Email Transport Adapter

**Branch**: `023-user-accounts` | **Source**: spec FR-022, edge cases | **Date**: 2026-05-09

Defines the `EmailTransport` ABC, the v1 `NoopEmailTransport` adapter, and the reservation contract for the follow-up `smtp` / `ses` / `sendgrid` adapters. Cross-references research.md §4 and §6.

---

## ABC contract

```python
from typing import Literal, Protocol

EmailPurpose = Literal[
    'verification',
    'password_reset',
    'email_change_new',
    'email_change_old_notify',
    'account_delete_export',
]


class EmailTransport(Protocol):
    """Process-scope adapter for outbound email.

    Selected at startup via SACP_EMAIL_TRANSPORT (one of: noop, smtp, ses, sendgrid).
    v1 ships only the noop adapter; smtp/ses/sendgrid raise NotImplementedError at startup.

    Spec 023 FR-022. Research.md §4, §6.
    """

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        purpose: EmailPurpose,
    ) -> None:
        """Emit one outbound email.

        Implementations MUST be idempotent on caller-controlled retry — the caller
        retries on transient failure, the transport MUST NOT enqueue duplicate sends.

        Implementations MUST NOT log `body` content (it contains the verification
        code or export bundle); only `purpose`, `to` (hashed), and `len(body)` may
        appear in audit-log payloads.

        Raises:
            EmailTransportUnavailable: when the transport cannot deliver. Caller
                falls back to admin_audit_log-only recording per spec 023 edge case.
        """
        ...
```

### Method signature rationale

- **Async**: FastAPI's request handlers are async-native; SMTP/SES/SendGrid I/O is async-friendly. Sync-from-the-start would force a future breaking change (research.md §4).
- **Keyword-only args**: enforces call-site readability for the security-sensitive `to` and `purpose` fields.
- **One method, `purpose` enum**: rejected the per-purpose-method shape (`send_verification`, `send_reset`, ...) as Liskov-violating and growth-hostile; future purposes add an enum value, not an ABC method.

---

## v1: `NoopEmailTransport`

The default and only operational adapter in v1.

### Behavior

`send(...)` writes a structured `admin_audit_log` row with `action='account_email_noop_emitted'` and payload:

```json
{
  "purpose": "verification",
  "to_hashed": "<HMAC-SHA256 of `to`, using SACP_AUTH_LOOKUP_KEY>",
  "subject": "Verify your SACP account",
  "body_length": 412
}
```

Then returns. No outbound network call.

### Body content NOT logged

The `body` content is NOT included in the audit-log payload. The verification / reset / email-change / export payload exists in the body and is sensitive. The associated `admin_audit_log` row for the code itself (e.g., `account_verification_emitted`) carries the HMAC-hashed code — operators who need to retrieve the plaintext code in dev read the noop adapter's row alongside the code-emit row.

In dev, retrieving a verification code:

```sql
-- Read both rows together:
SELECT at, action, payload FROM admin_audit_log
WHERE action IN ('account_verification_emitted', 'account_email_noop_emitted')
  AND target_id = 'acct_…'
ORDER BY at DESC
LIMIT 2;
```

The plaintext is reconstructed by the operator's mental model (or a small dev helper that joins both rows and prints the code from the payload's plaintext blob — emitted only when the noop adapter is selected, and ONLY in dev/staging deployments per the cross-condition WARN).

### Implementation note

The "plaintext blob" handling above is the only place the plaintext code touches durable state in the noop path. This is the dev/staging convenience that the cross-condition WARN flags as production-unsafe. The plaintext field is named `_dev_plaintext` and is scrubbed by the FR-014 ScrubFilter from any log emission OUTSIDE the audit-log INSERT path.

---

## Reserved adapters: `smtp`, `ses`, `sendgrid`

These three enum values are syntactically valid members of the `SACP_EMAIL_TRANSPORT` enum but are unimplemented in v1. Per `/speckit.analyze` finding 23-F1 (2026-05-13, fix 2026-05-14), the V16 validator rejects them at startup so the process exits before binding ports rather than booting and crashing on the first email send — a fail-open hole that opened when the original "factory raises at startup" plan was not wired into any production call path. The factory in `src/accounts/email_transport.py` retains the `EmailTransportNotImplemented` raise as a belt-and-braces guard for any code path that bypasses the validator. The factory raises:

```python
class EmailTransportNotImplemented(RuntimeError):
    """SACP_EMAIL_TRANSPORT={smtp,ses,sendgrid} reserved for follow-up spec.

    v1 supports only 'noop'. See specs/023-user-accounts/contracts/email-transport.md.
    """


def make_email_transport(name: str) -> EmailTransport:
    if name == 'noop':
        return NoopEmailTransport()
    if name in ('smtp', 'ses', 'sendgrid'):
        raise EmailTransportNotImplemented(
            f"SACP_EMAIL_TRANSPORT={name!r} is reserved for a follow-up spec; "
            f"v1 supports only 'noop'. See specs/023-user-accounts/contracts/email-transport.md."
        )
    raise ValueError(f"Unknown SACP_EMAIL_TRANSPORT value: {name!r}")
```

Startup enforcement happens at the V16 validator layer (`validate_email_transport()` in `src/config/validators.py`): an unimplemented value yields a `ValidationFailure` from `validate_all()`, which `src/run_apps.py:_run_validation()` reports and exits on before binding ports. The factory's `EmailTransportNotImplemented` raise is retained as a belt-and-braces guard for any code path that bypasses the validator. Operators see the ERROR in startup logs either way.

### Future implementation (follow-up spec)

The follow-up spec ("spec 026 email-transport" provisional) lands real implementations. Each implementation MUST:

1. Conform to the `EmailTransport` Protocol exactly.
2. Add its dependency to `pyproject.toml` (e.g., `boto3` for SES, `sendgrid-python` for SendGrid). `smtp` uses stdlib `smtplib` wrapped in `asyncio.to_thread`.
3. Add a `SACP_EMAIL_<TRANSPORT>_*` env var family for transport-specific config (host, port, credentials, region, etc.). Each new env var lands a validator + `docs/env-vars.md` section per V16.
4. Add a transport-specific test surface (`tests/test_026_smtp_transport.py` etc.).
5. Update this contract file (or supersede it with the follow-up spec's contract) to document the real-transport behavior.

The future spec MAY change the noop adapter's audit-row shape (e.g., to drop the `_dev_plaintext` field once real transports exist). Such a change is a contract amendment, not a breaking change in v1's sense.

---

## Failure semantics

### Transport raises `EmailTransportUnavailable`

Caller (the account-service flow) catches the exception, records the failure in `admin_audit_log` with `action='account_email_send_failed'`, and proceeds with the operation. The verification / reset / change / delete / export operation is NOT gated on email transport availability:

- **Verification email fails to send**: account stays in `pending_verification`; the code is recorded in `admin_audit_log` for operator-side recovery (operator can retrieve and email manually).
- **Password reset email fails to send**: reset flow returns success to the caller (no info leak about whether the email exists); the code is recorded in `admin_audit_log`; user retries or contacts operator.
- **Email change verification fails to send**: change request is held in `account_email_change_emitted` state; user retries via re-issuing the change request.
- **Account deletion export email fails to send**: deletion proceeds (credentials zeroed, status flipped); failed export is logged. Operator can re-fetch via spec 010 debug-export and email manually.

This privacy-preserving default is locked by the spec edge cases and clarify Q3 (operators legitimately run dev/staging with noop).

---

## Cross-spec references

- **Spec 010 (debug-export)** — the export shape consumed by `purpose='account_delete_export'`. The deletion flow calls the spec 010 internal export function, marshals the result through `body`, and routes through this transport.
- **Spec 007 (ai-security-pipeline) §FR-012** — ScrubFilter coverage extends to email body content. Implementation: scrub `body` from any log statement emitted by `EmailTransport.send` callers (the body is passed to the transport but never logged).

---

## Test obligations

- `test_023_account_create.py` covers `NoopEmailTransport.send(purpose='verification', ...)`: asserts the audit-log row is written with the documented shape, body NOT logged, plaintext code retrievable via the cross-row read.
- `test_023_email_change.py` covers `NoopEmailTransport.send(purpose='email_change_new', ...)` AND `purpose='email_change_old_notify', ...)` — both rows present.
- `test_023_account_delete.py` covers `NoopEmailTransport.send(purpose='account_delete_export', ...)` — body length matches export payload size; deletion proceeds on transport success AND on transport failure (separate tests).
- `test_023_validators.py` covers the `smtp`/`ses`/`sendgrid` V16-rejection path: `SACP_EMAIL_TRANSPORT=smtp` (or `ses` / `sendgrid`) yields a `ValidationFailure` from `validate_email_transport()` whose reason string includes "follow-up". The factory-level `EmailTransportNotImplemented` raise is covered by `tests/test_023_email_transport.py` as the belt-and-braces guard.
- `test_023_scrub_filter.py` covers `body` content scrubbing — emit a code via `NoopEmailTransport.send`, assert the body's plaintext does NOT appear in any log line outside the audit-log INSERT.
