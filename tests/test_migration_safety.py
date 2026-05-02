"""001 migration-safety CI gates (Phase F, fix/001-migration-safety).

Static analysis of `alembic/versions/*.py`. These tests are DB-free —
they import each migration module and inspect its source / metadata.

Covers audit-plan items:

* Forward-only invariant (FR-017): every migration from revision 008
  onward (the codification point) MUST have a `downgrade()` body that
  is `pass`. Pre-008 migrations are grandfathered (they shipped before
  FR-017 was codified) but a CI guard tracks the boundary.
* Revision metadata integrity: every migration declares a `revision`
  string, a `down_revision` (or `None` for the initial), and the
  filename's leading number matches the declared revision.
* No new destructive operations: any migration on the forward-only
  boundary that adds a `DROP TABLE` / `DROP COLUMN` to its `upgrade()`
  is flagged — the upgrade path itself is the canonical source of
  destructive changes and operators need explicit approval per the
  destructive-migration approval-gate item.
* Migration-replay / partial-failure / idempotency: DB-backed; markers
  pin the activation triggers for the deferred runtime tests.
"""

from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_ALEMBIC_DIR = REPO_ROOT / "alembic" / "versions"

# Migration revision at which FR-017 was codified. Earlier migrations
# (001-007) shipped with real downgrade() bodies and are grandfathered;
# 008+ MUST be `pass`-only.
_FORWARD_ONLY_FROM = "008"


def _migration_files() -> list[Path]:
    """Return migration files sorted by revision number."""
    return sorted(_ALEMBIC_DIR.glob("[0-9][0-9][0-9]_*.py"))


def _load_migration(path: Path) -> object:
    """Import a migration file as a module (no DB connection required)."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _downgrade_source(mod: object) -> str:
    fn = getattr(mod, "downgrade", None)
    return inspect.getsource(fn) if fn is not None else ""


def _upgrade_source(mod: object) -> str:
    fn = getattr(mod, "upgrade", None)
    return inspect.getsource(fn) if fn is not None else ""


def _downgrade_body_is_pass(mod: object) -> bool:
    """True when downgrade() is the documented forward-only no-op shape."""
    src = _downgrade_source(mod)
    if not src:
        return False
    body_lines = _strip_to_statements(src.splitlines()[1:])
    return body_lines == ["pass"]


def _strip_to_statements(lines: list[str]) -> list[str]:
    """Remove blanks, comments, and docstrings; return remaining statements."""
    out: list[str] = []
    in_docstring = False
    quote: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if in_docstring:
            if quote and quote in line:
                in_docstring = False
            continue
        if line.startswith(('"""', "'''")):
            q = line[:3]
            if line.count(q) >= 2:
                continue
            in_docstring = True
            quote = q
            continue
        out.append(line)
    return out


# ---------------------------------------------------------------------------
# FR-017: forward-only invariant from migration 008+
# ---------------------------------------------------------------------------


def test_fr017_post_codification_migrations_have_pass_downgrade() -> None:
    """From revision 008 onward, every downgrade() body MUST be `pass`.

    Pre-008 migrations (001-007) shipped before FR-017 was codified and
    have real downgrade bodies; they are grandfathered. The boundary is
    pinned at `_FORWARD_ONLY_FROM` and any new migration that violates it
    will fail this test on its own commit.
    """
    offenders: list[str] = []
    for path in _migration_files():
        revision = path.stem.split("_", 1)[0]
        if revision < _FORWARD_ONLY_FROM:
            continue
        mod = _load_migration(path)
        if not _downgrade_body_is_pass(mod):
            offenders.append(path.name)
    assert not offenders, (
        f"FR-017 violation: forward-only migrations 008+ must have a `pass` "
        f"downgrade body. Offenders: {offenders}"
    )


def test_fr017_post_codification_downgrades_have_no_drop_or_alter() -> None:
    """Pass-shaped downgrade can't accidentally include destructive ops."""
    offenders: list[tuple[str, str]] = []
    for path in _migration_files():
        revision = path.stem.split("_", 1)[0]
        if revision < _FORWARD_ONLY_FROM:
            continue
        mod = _load_migration(path)
        src = _downgrade_source(mod).upper()
        for verb in ("DROP TABLE", "DROP COLUMN", "DROP INDEX", "ALTER TABLE"):
            if verb in src:
                offenders.append((path.name, verb))
    assert not offenders, (
        f"FR-017 violation: post-codification downgrade contains destructive "
        f"verb. Offenders: {offenders}"
    )


# ---------------------------------------------------------------------------
# Revision metadata integrity
# ---------------------------------------------------------------------------


def test_every_migration_has_required_metadata() -> None:
    """Every migration declares revision, down_revision, upgrade, downgrade."""
    missing: list[tuple[str, str]] = []
    for path in _migration_files():
        mod = _load_migration(path)
        for attr in ("revision", "down_revision", "upgrade", "downgrade"):
            if not hasattr(mod, attr):
                missing.append((path.name, attr))
    assert not missing, f"Migrations missing required metadata: {missing}"


def test_revision_string_matches_filename_prefix() -> None:
    """The 3-digit filename prefix matches the migration's `revision` string."""
    mismatches: list[tuple[str, str, str]] = []
    for path in _migration_files():
        mod = _load_migration(path)
        prefix = path.stem.split("_", 1)[0]
        revision = getattr(mod, "revision", "")
        if revision != prefix:
            mismatches.append((path.name, prefix, revision))
    assert (
        not mismatches
    ), f"Filename prefix must match migration.revision. Mismatches: {mismatches}"


def test_revision_chain_is_contiguous() -> None:
    """Each migration's `down_revision` points at the previous in revision order."""
    files = _migration_files()
    pairs = []
    for path in files:
        mod = _load_migration(path)
        pairs.append((path.name, mod.revision, mod.down_revision))
    # The first migration in the chain has down_revision = None.
    assert pairs[0][2] is None, f"First migration ({pairs[0][0]}) must have down_revision=None"
    # Each subsequent migration's down_revision must equal the previous revision.
    for prev, current in zip(pairs, pairs[1:], strict=False):
        assert current[2] == prev[1], (
            f"Chain break: {current[0]} declares down_revision={current[2]!r} "
            f"but predecessor {prev[0]} has revision={prev[1]!r}"
        )


# ---------------------------------------------------------------------------
# Destructive-migration approval gate (upgrade-side)
# ---------------------------------------------------------------------------


def test_upgrade_destructive_ops_are_documented_at_revision_boundary() -> None:
    """No new migration introduces an undocumented destructive op.

    DROP TABLE / DROP COLUMN in upgrade() destroy data. Any such op MUST
    carry a comment block explaining the operator-approval rationale, OR
    the migration must be reviewed and grandfathered before this gate.
    Pre-008 migrations are grandfathered; 008+ failing this gate must
    either remove the destructive op or add the approval-rationale block.
    """
    findings: list[tuple[str, str]] = []
    for path in _migration_files():
        revision = path.stem.split("_", 1)[0]
        if revision < _FORWARD_ONLY_FROM:
            continue
        mod = _load_migration(path)
        src = _upgrade_source(mod)
        upper = src.upper()
        approval_re = re.compile(r"#\s*(approved|operator[-_ ]approval)", re.IGNORECASE)
        for verb in ("DROP TABLE", "DROP COLUMN"):
            # Approval comment is required in the same function as the
            # destructive verb so human review is recorded inline.
            if verb in upper and not approval_re.search(src):
                findings.append((path.name, verb))
    assert not findings, (
        f"Destructive upgrade op without operator-approval comment. "
        f"Add a `# approved by <reviewer>` annotation. Offenders: {findings}"
    )


# ---------------------------------------------------------------------------
# Migration catalog: presence + count sanity
# ---------------------------------------------------------------------------


def test_migration_catalog_is_non_empty_and_growing() -> None:
    """Sanity: at least one migration ships in the catalog."""
    files = _migration_files()
    assert len(files) >= 1, "no alembic migrations found"
    # Bound at a generous ceiling so test failures here surface intentional
    # boundary changes rather than an explosion of migration sprawl.
    assert (
        len(files) < 100
    ), "100+ migrations — review whether some can be squashed at a Phase boundary"


# ---------------------------------------------------------------------------
# DB-backed tests (deferred markers)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="DB-backed: deferred. Trigger: cross-spec integration audit.")
def test_migration_idempotency_deferred() -> None:
    """`upgrade head` twice is a no-op on the second run.

    Activation: when the cross-spec integration test tier ships a Postgres
    fixture that can run `alembic upgrade head` then `alembic upgrade head`
    again, replace this skip with the real test.
    """


@pytest.mark.skip(reason="DB-backed: deferred. Trigger: cross-spec integration audit.")
def test_migration_replay_from_empty_db_deferred() -> None:
    """Full migration chain replays from an empty DB end-to-end.

    Activation: cross-spec integration test tier with a fresh Postgres
    fixture per run.
    """


@pytest.mark.skip(reason="DB-backed: deferred. Trigger: Phase 3 disaster-recovery audit.")
def test_restore_from_old_backup_compatibility_deferred() -> None:
    """Restore-from-vN backup auto-migrates to current schema cleanly.

    Activation: Phase 3 disaster-recovery audit codifies the backup-format
    test fixture catalog.
    """


@pytest.mark.skip(reason="DB-backed: deferred. Trigger: Phase 3 multi-instance scaling audit.")
def test_migration_locking_under_concurrent_startup_deferred() -> None:
    """Two orchestrator processes starting simultaneously: one wins the lock.

    Activation: Phase 3 multi-instance topology adds the alembic-lock
    contract; today single-instance topology makes this a no-op.
    """
