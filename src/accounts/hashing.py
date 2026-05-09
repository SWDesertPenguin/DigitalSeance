# SPDX-License-Identifier: AGPL-3.0-or-later

"""Argon2id password hashing wrapper for spec 023 (FR-003, SC-005, SC-007).

Wraps :mod:`argon2` (the ``argon2-cffi`` PyPI package, pinned in
``pyproject.toml`` per Constitution §6.3) so the rest of the codebase
never touches the third-party API directly. A future swap to a
different argon2id implementation is an internal-architecture refactor,
not an FR-021 boundary change.

See ``specs/023-user-accounts/research.md`` §1 (library choice) and
§8 (transparent re-hash on parameter change) for the design notes.
"""
