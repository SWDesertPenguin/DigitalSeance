# Contract: New Environment Variables (V16)

**Branch**: `023-user-accounts` | **Source**: spec FR-022, Configuration (V16) section | **Date**: 2026-05-09

Seven new `SACP_*` environment variables. Per Constitution V16, each MUST have a validator function in `src/config/validators.py` (registered in the `VALIDATORS` tuple) AND a corresponding section in `docs/env-vars.md` with the six standard fields BEFORE `/speckit.tasks` runs (FR-022 — V16 deliverable gate).

The six standard fields per `docs/env-vars.md` convention: Default, Type, Valid range, Blast radius, Validation rule, Source spec.

---

## `SACP_ACCOUNTS_ENABLED`

| Field | Value |
|---|---|
| **Default** | `0` (master switch ships off; operators opt in) |
| **Type** | bool-style enum |
| **Valid range** | `0` \| `1` |
| **Blast radius** | Master switch for the entire account surface. When `0`, all seven account endpoints + `GET /me/sessions` return HTTP 404; SPA falls back to token-paste landing (FR-018). When `1`, the surface is mounted. |
| **Validation rule** | `value in {'0', '1'}` else fail-closed exit. |
| **Source spec** | spec 023 FR-018, FR-022 |

---

## `SACP_PASSWORD_ARGON2_TIME_COST`

| Field | Value |
|---|---|
| **Default** | `2` |
| **Type** | positive integer |
| **Valid range** | `[1, 10]` per OWASP 2024 envelope |
| **Blast radius** | Applies to ALL new password hashes (creation + re-hash). Existing hashes verify with their stored params. Below `1` is cryptographically inadequate; above `10` introduces unacceptable login latency on commodity hardware. |
| **Validation rule** | parses-as-int AND `1 <= value <= 10` else fail-closed exit. Below the OWASP minimum (`1`) MUST emit a startup WARNING; below it AND above the documented insecure-floor MUST be rejected outright. |
| **Source spec** | spec 023 FR-003, FR-022 |

---

## `SACP_PASSWORD_ARGON2_MEMORY_COST_KB`

| Field | Value |
|---|---|
| **Default** | `19456` (19 MiB) per OWASP 2024 password-storage cheat sheet |
| **Type** | positive integer (kilobytes) |
| **Valid range** | `[7168, 1048576]` (7 MiB to 1 GiB) |
| **Blast radius** | Applies to ALL new password hashes. Below the floor produces a startup error; above the ceiling produces a startup warning (memory exhaustion risk on small instances). |
| **Validation rule** | parses-as-int AND `7168 <= value <= 1048576` else fail-closed exit. |
| **Source spec** | spec 023 FR-003, FR-022 |

---

## `SACP_ACCOUNT_SESSION_TTL_HOURS`

| Field | Value |
|---|---|
| **Default** | `168` (7 days) |
| **Type** | positive integer |
| **Valid range** | `[1, 8760]` (1 hour to 1 year) |
| **Blast radius** | Applies to all account login cookie issuance. The cookie's `Max-Age` is set from this value. After expiry, re-login is required. |
| **Validation rule** | parses-as-int AND `1 <= value <= 8760` else fail-closed exit. |
| **Source spec** | spec 023 FR-017, FR-022 |

---

## `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN`

| Field | Value |
|---|---|
| **Default** | `10` |
| **Type** | positive integer |
| **Valid range** | `[1, 1000]` |
| **Blast radius** | Per-IP login + create-account rate-limit threshold. Limit exceedance returns HTTP 429 + `Retry-After`. Separate from spec 019's general per-IP network-layer limiter; both apply additively (FR-015). |
| **Validation rule** | parses-as-int AND `1 <= value <= 1000` else fail-closed exit. |
| **Source spec** | spec 023 FR-015, FR-022 |

---

## `SACP_EMAIL_TRANSPORT`

| Field | Value |
|---|---|
| **Default** | `noop` (development-friendly; codes appear in `admin_audit_log` only) |
| **Type** | string enum |
| **Valid range** | `noop` \| `smtp` \| `ses` \| `sendgrid` |
| **Blast radius** | Selects the `EmailTransport` adapter. v1 ships only `noop`; the other three values are RESERVED — selection raises `NotImplementedError` at startup with a pointer to `contracts/email-transport.md`. Operators needing real transport defer enabling accounts until the follow-up spec ships. |
| **Validation rule** | `value in {'noop', 'smtp', 'ses', 'sendgrid'}` else fail-closed exit. The `smtp`/`ses`/`sendgrid` values pass syntactic validation but fail at adapter instantiation (clear ERROR naming the follow-up spec). |
| **Source spec** | spec 023 FR-022, Configuration (V16) section |

---

## `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`

| Field | Value |
|---|---|
| **Default** | `7` |
| **Type** | non-negative integer |
| **Valid range** | `[0, 365]` |
| **Blast radius** | Reserves a deleted account's email address for re-registration during the configured window. `0` disables the grace period entirely (immediate email release on deletion). `365` caps the maximum reservation window at one year. Operators with stricter or looser retention policies tune this knob. |
| **Validation rule** | parses-as-int AND `0 <= value <= 365` else fail-closed exit. |
| **Source spec** | spec 023 FR-013, FR-022 (added 2026-05-09 per clarify Q5) |

---

## Cross-validator interaction

When `SACP_ACCOUNTS_ENABLED=1` AND `SACP_EMAIL_TRANSPORT=noop` simultaneously, the orchestrator MUST emit a startup WARNING (NOT a fail-closed exit) per FR-022 / clarify Q3. Implementation pattern (research.md §13):

```python
def emit_accounts_email_transport_warning() -> None:
    """Called from startup banner code AFTER validators pass."""
    accounts = os.environ.get("SACP_ACCOUNTS_ENABLED", "0")
    transport = os.environ.get("SACP_EMAIL_TRANSPORT", "noop")
    if accounts == "1" and transport == "noop":
        logger.warning(
            "SACP_ACCOUNTS_ENABLED=1 with SACP_EMAIL_TRANSPORT=noop: "
            "verification, reset, and notification codes will appear in "
            "admin_audit_log only. Not suitable for production."
        )
```

The WARN is emitted from a separate function (`emit_accounts_email_transport_warning()`), NOT from a `ValidationFailure`-returning validator, so V16's fail-closed contract isn't tainted (failures abort startup; warnings don't).

---

## Validator implementation pattern

All seven validators follow the existing `src/config/validators.py` pattern (matches spec 025's pattern documented in `specs/025-session-length-cap/contracts/env-vars.md`):

```python
def validate_accounts_enabled() -> ValidationFailure | None:
    """SACP_ACCOUNTS_ENABLED: '0' or '1', default '0'. Master switch (spec 023 FR-018)."""
    return _validate_bool_enum("SACP_ACCOUNTS_ENABLED")


def validate_password_argon2_time_cost() -> ValidationFailure | None:
    """SACP_PASSWORD_ARGON2_TIME_COST: int in [1, 10], default 2. Spec 023 FR-003."""
    val = os.environ.get("SACP_PASSWORD_ARGON2_TIME_COST")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure("SACP_PASSWORD_ARGON2_TIME_COST", f"must be integer; got {val!r}")
    if not 1 <= num <= 10:
        return ValidationFailure("SACP_PASSWORD_ARGON2_TIME_COST", f"must be in [1, 10]; got {num}")
    return None
```

Each validator is registered in the `VALIDATORS` tuple at module bottom. Startup walks the tuple and raises before any port is bound — matches V16's "validate before binding" rule.

---

## docs/env-vars.md sections

The same seven vars get sections in `docs/env-vars.md` with the same six fields (rendered as a table per existing convention in that file). The validator and the doc section MUST land together in the same task per FR-022; CI's V16 gate flags any var with a validator but no doc section, and vice versa.

---

## Test obligations

- `test_023_validators.py` covers each of the seven validators:
  - Valid value passes.
  - Out-of-range value raises `ConfigValidationError` with the offending var name.
  - Empty value (where defaulted) uses default.
  - Non-parseable value raises (e.g., `'abc'` for an int field).
- `test_023_validators.py` covers the V16 startup gate: invalid value at startup MUST exit before binding ports.
- `test_023_validators.py` covers the cross-condition WARN: `SACP_ACCOUNTS_ENABLED=1` + `SACP_EMAIL_TRANSPORT=noop` emits a WARN log line; validators themselves still pass (no `ValidationFailure`).
- `test_023_validators.py` covers the `SACP_EMAIL_TRANSPORT={smtp,ses,sendgrid}` startup-error path — the validator passes, but the adapter factory raises `NotImplementedError` with the documented message.
- `test_023_validators.py` covers below-floor argon2id parameters (e.g., `SACP_PASSWORD_ARGON2_TIME_COST=1` is valid but emits an OWASP-floor WARN).
