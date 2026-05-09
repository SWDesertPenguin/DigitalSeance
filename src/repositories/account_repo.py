# SPDX-License-Identifier: AGPL-3.0-or-later

"""``accounts`` + ``account_participants`` repository for spec 023.

Phase 2 skeleton; CRUD entry points (``create_account``,
``get_account_by_id``, ``get_account_by_email_for_login``,
``update_account_email``, ``update_account_password_hash``,
``mark_account_deleted``, ``update_last_login_at``,
``link_participant_to_account``, ``list_participants_for_account``,
``list_sessions_for_account``) land alongside the service layer in
Phase 3+ tasks.

See ``specs/023-user-accounts/data-model.md`` for the schema and the
cross-column application-side rules and
``specs/023-user-accounts/research.md`` §9 for the
``/me/sessions`` query shape.
"""
