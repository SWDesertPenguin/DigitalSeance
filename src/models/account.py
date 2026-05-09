# SPDX-License-Identifier: AGPL-3.0-or-later

"""Account + AccountParticipant value types for spec 023.

Phase 2 skeleton; the frozen :class:`Account` and
:class:`AccountParticipant` dataclasses land alongside the service
layer in Phase 3+ tasks. The transient code value types
(:class:`VerificationCode`, :class:`ResetCode`,
:class:`EmailChangeToken`) are documented here for cross-reference
but their implementation lives in ``src/accounts/codes.py``.

See ``specs/023-user-accounts/data-model.md`` for the field shape
backing each entity.
"""
