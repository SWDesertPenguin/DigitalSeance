# SPDX-License-Identifier: AGPL-3.0-or-later

"""Single-use verification + reset code primitives for spec 023.

Generates 16-character Crockford base32 codes via
:func:`secrets.token_bytes` and HMAC-SHA256-hashes them with
``SACP_AUTH_LOOKUP_KEY`` for durable storage in ``admin_audit_log``
rows. Plaintext codes are never persisted; they pass through the email
transport once and live in operator-side memory only.

See ``specs/023-user-accounts/contracts/codes.md`` for the full
contract and ``specs/023-user-accounts/research.md`` §3 for the
audit-log-only persistence rationale.
"""
