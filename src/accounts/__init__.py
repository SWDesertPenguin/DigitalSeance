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
