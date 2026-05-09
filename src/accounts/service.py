# SPDX-License-Identifier: AGPL-3.0-or-later

"""Account-service orchestration for spec 023.

Phase 2 skeleton; the ``create_account`` / ``verify_account`` /
``login`` / ``request_email_change`` / ``confirm_email_change`` /
``change_password`` / ``delete_account`` / ``list_sessions`` entry
points land in Phase 3+ alongside their tests. Until then the module
documents the intended surface so future task handlers slot the
implementations in without re-deriving the contract.

Cross-references:

- Spec 023 ``contracts/account-endpoints.md`` — endpoint payload shape.
- Spec 023 ``research.md`` §1 (argon2id), §3 (codes), §5 (rate
  limiter), §10 (SessionStore extension).
- Spec 023 ``contracts/audit-log-events.md`` — emitted audit-row
  shapes.
"""
