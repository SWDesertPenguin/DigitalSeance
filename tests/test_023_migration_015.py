# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 alembic 015 migration tests (T020 of tasks.md).

Static analysis of `alembic/versions/015_user_accounts.py`. DB-free —
imports the migration module and inspects its source / metadata against
the spec 023 data-model contract. The DB-backed upgrade/downgrade
exercise is covered by the existing test_schema_mirror.py + the per-test
migration fixture in conftest.py (which builds the schema from the raw
DDL mirror, NOT alembic — per memory `feedback_test_schema_mirror`).

Asserts:

  - Revision metadata: revision='015', down_revision='014',
    branch_labels=None, depends_on=None.
  - Forward-only invariant per Constitution §6 + 001 §FR-017: downgrade()
    body is `pass`.
  - upgrade() creates both `accounts` and `account_participants` tables
    with the columns documented in data-model.md.
  - The partial unique email index is created with the
    `WHERE status IN ('pending_verification', 'active')` predicate
    (research.md §2 — the partial-index pattern is what enables a deleted
    account to coexist with a fresh registration after the grace window).
  - The account_participants FKs match the data-model contract:
    account_id ON DELETE RESTRICT (FR-012's preserve-row-on-delete);
    participant_id ON DELETE CASCADE + UNIQUE (FR-002's
    at-most-one-account-per-participant invariant).
  - The btree index on account_participants.account_id (research §9 —
    primary lookup for /me/sessions).
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MIGRATION_PATH = REPO_ROOT / "alembic" / "versions" / "015_user_accounts.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("alembic_015", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _upgrade_source() -> str:
    return inspect.getsource(_load().upgrade)


def _all_source() -> str:
    """Concatenated source of every helper called by upgrade()."""
    mod = _load()
    parts: list[str] = []
    for name in dir(mod):
        obj = getattr(mod, name)
        if callable(obj) and not name.startswith("__"):
            with contextlib.suppress(OSError, TypeError):
                parts.append(inspect.getsource(obj))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Revision metadata
# ---------------------------------------------------------------------------


def test_revision_is_015() -> None:
    mod = _load()
    assert mod.revision == "015"


def test_down_revision_is_014() -> None:
    """Pre-allocated slot per the dispatcher's brief: down_revision='014'.
    Slot 014 is taken by spec 029's audit-log-session-timestamp index."""
    mod = _load()
    assert mod.down_revision == "014"


def test_branch_labels_and_depends_on_are_none() -> None:
    mod = _load()
    assert mod.branch_labels is None
    assert mod.depends_on is None


# ---------------------------------------------------------------------------
# Forward-only invariant (Constitution §6 + 001 §FR-017)
# ---------------------------------------------------------------------------


def test_downgrade_is_no_op() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    src = inspect.getsource(_load().downgrade)
    body_lines = [
        line.strip()
        for line in src.splitlines()[1:]
        if line.strip() and not line.strip().startswith("#")
    ]
    # Strip docstring lines.
    body_lines = [line for line in body_lines if not line.startswith(('"""', "'''"))]
    assert "pass" in body_lines


# ---------------------------------------------------------------------------
# accounts table
# ---------------------------------------------------------------------------


def test_creates_accounts_table() -> None:
    src = _all_source().upper()
    assert "CREATE TABLE ACCOUNTS" in src


def test_accounts_has_uuid_primary_key() -> None:
    src = _all_source()
    assert "ID UUID PRIMARY KEY".upper() in src.upper()


def test_accounts_has_status_check_constraint() -> None:
    """status CHECK ('pending_verification', 'active', 'deleted')."""
    src = _all_source()
    assert "pending_verification" in src
    assert "'active'" in src
    assert "'deleted'" in src


def test_accounts_status_default_is_pending_verification() -> None:
    src = _all_source()
    assert "DEFAULT 'pending_verification'" in src


def test_accounts_has_email_grace_release_at_column() -> None:
    """FR-013 / SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS — populated at
    deletion time = deleted_at + (env_var * interval '1 day')."""
    src = _all_source()
    assert "email_grace_release_at" in src.lower()


def test_accounts_has_partial_unique_email_index() -> None:
    """research.md §2: partial unique on (email) WHERE status IN
    ('pending_verification', 'active'). Lets a deleted-account row
    coexist with a fresh registration on the same email after grace
    period elapses, while still blocking duplicate active accounts."""
    src = _all_source().upper()
    assert "CREATE UNIQUE INDEX ACCOUNTS_EMAIL_ACTIVE_UIDX" in src
    assert "WHERE STATUS IN" in src


# ---------------------------------------------------------------------------
# account_participants table
# ---------------------------------------------------------------------------


def test_creates_account_participants_table() -> None:
    src = _all_source().upper()
    assert "CREATE TABLE ACCOUNT_PARTICIPANTS" in src


def test_account_participants_account_fk_is_restrict() -> None:
    """FR-012's preserve-row-on-delete contract: deleting an account
    outright would orphan participant ownership; the spec requires
    zeroing credentials but preserving the row."""
    src = _all_source().upper()
    assert "REFERENCES ACCOUNTS(ID) ON DELETE RESTRICT" in src


def test_account_participants_participant_fk_is_cascade() -> None:
    """research.md §9 + FR-002: when a participant row is deleted the
    join row goes with it."""
    src = _all_source().upper()
    assert "REFERENCES PARTICIPANTS(ID) ON DELETE CASCADE" in src


def test_account_participants_participant_id_is_unique() -> None:
    """FR-002: a participant belongs to at most one account."""
    src = _all_source()
    # The UNIQUE keyword appears on participant_id within the column list.
    assert "participant_id TEXT NOT NULL UNIQUE" in src


def test_account_participants_has_account_id_btree_index() -> None:
    """research.md §9: btree on account_id is the primary lookup index
    for the /me/sessions JOIN."""
    src = _all_source().upper()
    assert "CREATE INDEX ACCOUNT_PARTICIPANTS_ACCOUNT_IDX" in src
    assert "(ACCOUNT_ID)" in src


# ---------------------------------------------------------------------------
# upgrade() composes both helpers
# ---------------------------------------------------------------------------


def test_upgrade_calls_both_table_helpers() -> None:
    """upgrade() composes _create_accounts + _create_account_participants;
    no other side effects expected at this revision."""
    src = _upgrade_source()
    assert "_create_accounts" in src
    assert "_create_account_participants" in src
