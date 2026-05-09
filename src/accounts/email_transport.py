# SPDX-License-Identifier: AGPL-3.0-or-later

"""Email-transport ABC + noop adapter for spec 023.

Defines the :class:`EmailTransport` ``Protocol`` and the v1 default
:class:`NoopEmailTransport` adapter, plus the
:func:`select_transport` factory that reads ``SACP_EMAIL_TRANSPORT``
at startup and raises :class:`EmailTransportNotImplemented` for the
reserved ``smtp`` / ``ses`` / ``sendgrid`` values until the
follow-up email-transport spec lands.

See ``specs/023-user-accounts/contracts/email-transport.md`` for the
full contract and ``specs/023-user-accounts/research.md`` §4 + §6 for
the design notes.
"""
