# SPDX-License-Identifier: AGPL-3.0-or-later

"""User-accounts package for spec 023 (User Accounts).

Owns the application-side primitives that back the seven account-router
endpoints documented in
``specs/023-user-accounts/contracts/account-endpoints.md``: argon2id
password hashing, single-use verification / reset / email-change codes,
the email-transport ABC + noop adapter, the per-IP login rate limiter,
and the account-service orchestration layer that ties them to the
account repository and the spec 011 ``SessionStore``.

The package is ``import``-time side-effect-free; modules read
``SACP_*`` env vars only on construction of the relevant primitive
(``PasswordHasher``, ``LoginRateLimiter``, ``select_transport``). The
master-switch read (``SACP_ACCOUNTS_ENABLED``) lives in the route
mounting code at ``src/web_ui/app.py`` per FR-018.

See ``specs/023-user-accounts/research.md`` for the design notes
backing each submodule.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def should_mount_account_router() -> bool:
    """Return True iff the account-router should be mounted at startup.

    Two gates apply:

    1. ``SACP_ACCOUNTS_ENABLED`` master switch (FR-018). When unset or
       ``'0'``, the router stays unmounted and every account endpoint
       returns 404.
    2. ``SACP_TOPOLOGY`` is NOT ``'7'`` (research §12). Topology 7
       (MCP-to-MCP, Phase 3+) has no orchestrator-side account store;
       the gate emits a startup ERROR naming the cross-spec
       incompatibility and refuses to mount.

    Both checks are read on every call so tests can flip the state
    without restarting the process.
    """
    if not _accounts_enabled():
        return False
    if _topology_blocks_accounts():
        log.error(
            "Spec 023 account-router refused to mount: SACP_TOPOLOGY=7 has no "
            "orchestrator-side account store (research §12 / spec V12 — "
            "topologies 1-6 only). Unset SACP_ACCOUNTS_ENABLED or change "
            "SACP_TOPOLOGY to enable accounts."
        )
        return False
    return True


def _accounts_enabled() -> bool:
    """FR-018 master-switch read: ``SACP_ACCOUNTS_ENABLED == '1'``."""
    return os.environ.get("SACP_ACCOUNTS_ENABLED", "0") == "1"


def _topology_blocks_accounts() -> bool:
    """Research §12: topology 7 (MCP-to-MCP) has no account store."""
    return os.environ.get("SACP_TOPOLOGY", "").strip() == "7"


def emit_accounts_email_transport_warning() -> None:
    """Emit a startup WARN when accounts=1 + transport=noop (research §13).

    Production deployments should NOT run the noop adapter: verification,
    reset, and notification codes appear in ``admin_audit_log`` only,
    so account self-service relies on operator-side audit-log access.
    Dev / staging operators legitimately use noop (clarify Q3) so this
    is a WARN — not a ``ValidationFailure`` — to keep V16's fail-closed
    contract clean.
    """
    accounts = os.environ.get("SACP_ACCOUNTS_ENABLED", "0")
    transport = os.environ.get("SACP_EMAIL_TRANSPORT", "noop")
    if accounts == "1" and transport == "noop":
        log.warning(
            "SACP_ACCOUNTS_ENABLED=1 with SACP_EMAIL_TRANSPORT=noop: "
            "verification, reset, and notification codes will appear in "
            "admin_audit_log only. Not suitable for production."
        )
