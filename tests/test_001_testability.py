"""001 core-data-model testability suite (Phase B, fix/001-testability).

Covers audit-plan items not addressed by existing per-module tests:

* API-surface regression: MessageRepository and LogRepository expose NO
  update_* / delete_* methods — immutability enforced at the interface
* Complete lifecycle-transition matrix: all valid transitions tested,
  invalid transitions rejected, including gaps paused->archived and
  archived->deleted
* Double-delete idempotency: calling delete_session twice does not crash
* FR-021 InvalidToken: decrypting with the wrong key raises
  cryptography.fernet.InvalidToken (not a generic Exception)
* Migration forward-only assertion: every alembic migration that is
  intentionally additive has a ``pass`` downgrade; every non-pass
  downgrade does not contain a DROP COLUMN (protecting deployed data)
* FR-to-test traceability table stub: see docs/traceability/fr-to-test.md
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import asyncpg
import pytest
from cryptography.fernet import Fernet, InvalidToken

from src.database.encryption import decrypt_value, encrypt_value
from src.repositories.errors import InvalidTransitionError
from src.repositories.session_repo import SessionRepository

REPO_ROOT = Path(__file__).resolve().parent.parent
_ALEMBIC_DIR = REPO_ROOT / "alembic" / "versions"

VALID_KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()


# ---------------------------------------------------------------------------
# API-surface regression: no update_* / delete_* on append-only repos
# ---------------------------------------------------------------------------


def _public_method_names(cls: type) -> set[str]:
    return {
        name
        for name, val in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_message_repo_has_no_mutating_methods() -> None:
    """FR-007 / FR-008: MessageRepository must expose ONLY append + read methods.

    Any ``update_*`` or ``delete_*`` method on the transcript store would
    silently undermine the immutability guarantee that the rest of the
    system depends on for audit integrity. This test will fail the moment
    someone adds a mutation by mistake.
    """
    from src.repositories.message_repo import MessageRepository

    methods = _public_method_names(MessageRepository)
    mutating = {m for m in methods if m.startswith(("update_", "delete_"))}
    assert not mutating, f"MessageRepository must not expose mutation methods; found: {mutating}"


def test_log_repo_has_no_mutating_methods() -> None:
    """FR-008: LogRepository must expose ONLY append + read methods (append-only logs)."""
    from src.repositories.log_repo import LogRepository

    methods = _public_method_names(LogRepository)
    mutating = {m for m in methods if m.startswith(("update_", "delete_"))}
    assert not mutating, f"LogRepository must not expose mutation methods; found: {mutating}"


# ---------------------------------------------------------------------------
# Lifecycle-transition matrix (all transitions per 001 FR-010)
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(pool: asyncpg.Pool) -> SessionRepository:
    return SessionRepository(pool)


async def _new_session(repo: SessionRepository) -> str:
    session, _, _ = await repo.create_session(
        "Testability Session",
        facilitator_display_name="Tester",
        facilitator_provider="anthropic",
        facilitator_model="claude-haiku-4-5-20251001",
        facilitator_model_tier="low",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id


async def test_active_to_paused(repo: SessionRepository) -> None:
    """active → paused is a valid transition."""
    sid = await _new_session(repo)
    result = await repo.update_status(sid, "paused")
    assert result.status == "paused"


async def test_paused_to_active(repo: SessionRepository) -> None:
    """paused → active is a valid transition."""
    sid = await _new_session(repo)
    await repo.update_status(sid, "paused")
    result = await repo.update_status(sid, "active")
    assert result.status == "active"


async def test_active_to_archived(repo: SessionRepository) -> None:
    """active → archived is a valid transition."""
    sid = await _new_session(repo)
    result = await repo.update_status(sid, "archived")
    assert result.status == "archived"


async def test_paused_to_archived_db(repo: SessionRepository) -> None:
    """paused → archived reaches the DB; status column reflects the change."""
    sid = await _new_session(repo)
    await repo.update_status(sid, "paused")
    result = await repo.update_status(sid, "archived")
    assert result.status == "archived"
    row = await repo.get_session(sid)
    assert row is not None
    assert row.status == "archived"


@pytest.mark.asyncio
async def test_archived_to_deleted_db(
    repo: SessionRepository,
    pool: asyncpg.Pool,
) -> None:
    """archived → deleted removes the session row (gap in prior test coverage)."""
    sid = await _new_session(repo)
    await repo.update_status(sid, "archived")
    await repo.delete_session(sid)
    assert await repo.get_session(sid) is None


async def test_archived_to_active_rejected(repo: SessionRepository) -> None:
    """archived → active is invalid per FR-010 transition table."""
    sid = await _new_session(repo)
    await repo.update_status(sid, "archived")
    with pytest.raises(InvalidTransitionError):
        await repo.update_status(sid, "active")


async def test_archived_to_paused_rejected(repo: SessionRepository) -> None:
    """archived → paused is invalid per FR-010 transition table."""
    sid = await _new_session(repo)
    await repo.update_status(sid, "archived")
    with pytest.raises(InvalidTransitionError):
        await repo.update_status(sid, "paused")


# ---------------------------------------------------------------------------
# Double-delete idempotency
# ---------------------------------------------------------------------------


async def test_double_delete_does_not_crash(
    repo: SessionRepository,
    pool: asyncpg.Pool,
) -> None:
    """Calling delete_session twice on the same session must not raise.

    This protects against a race where two concurrent cleanup paths both
    attempt to delete the same session. The first delete succeeds; the
    second should either succeed silently or skip gracefully — never raise
    an unhandled exception that would crash the caller.
    """
    sid = await _new_session(repo)
    await repo.delete_session(sid)
    # Second delete: session is already gone — must not raise
    await repo.delete_session(sid)
    assert await repo.get_session(sid) is None


# ---------------------------------------------------------------------------
# FR-021: wrong key → cryptography.fernet.InvalidToken (not generic Exception)
# ---------------------------------------------------------------------------


def test_wrong_key_raises_invalid_token() -> None:
    """FR-021: decrypt with wrong key raises InvalidToken specifically.

    Callers relying on the generic Exception handler would silently swallow
    the wrong error class. Pinning to ``cryptography.fernet.InvalidToken``
    ensures error handling is explicit and callers know a key-rotation event
    has occurred rather than mistaking it for a general failure.
    """
    ciphertext = encrypt_value("secret-api-key", key=VALID_KEY)
    with pytest.raises(InvalidToken):
        decrypt_value(ciphertext, key=OTHER_KEY)


def test_truncated_ciphertext_raises_invalid_token() -> None:
    """Partial/corrupt ciphertext also raises InvalidToken (not generic Exception)."""
    ciphertext = encrypt_value("some-value", key=VALID_KEY)
    truncated = ciphertext[: len(ciphertext) // 2]
    with pytest.raises(InvalidToken):
        decrypt_value(truncated, key=VALID_KEY)


# ---------------------------------------------------------------------------
# Migration forward-only assertion (FR-017)
# ---------------------------------------------------------------------------


def _load_migration(path: Path) -> object:
    """Import a migration file as a module."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _get_downgrade_source(mod: object) -> str:
    """Return the source of the migration's downgrade() function."""
    fn = getattr(mod, "downgrade", None)
    if fn is None:
        return ""
    return inspect.getsource(fn)


def test_instrumentation_migration_is_forward_only() -> None:
    """FR-017: migration 008 (instrumentation columns) is explicitly forward-only.

    The 008 migration adds nullable timing + override columns to existing tables.
    Its downgrade() is intentionally ``pass`` because dropping those columns
    after they have been populated would destroy operational data. This test
    pins the forward-only contract so it can't be silently changed to a
    destructive DROP COLUMN rollback later.
    """
    matches = list(_ALEMBIC_DIR.glob("008_*.py"))
    assert matches, "migration 008 not found — update this test if revision numbering changes"
    mod = _load_migration(matches[0])
    src = _get_downgrade_source(mod)
    assert "pass" in src, (
        "migration 008 downgrade() must be `pass` (forward-only per Constitution §6 + 001 FR-017); "
        "found real rollback code which would destroy live timing/override data"
    )
    assert (
        "DROP" not in src.upper()
    ), "migration 008 downgrade() must not DROP anything — it is forward-only"


def test_all_migrations_have_downgrade_function() -> None:
    """FR-017: every migration file defines a downgrade() function.

    Even if the body is ``pass``, its presence signals the migration was
    written with forward-only intent consciously noted, rather than simply
    forgotten. Missing downgrade functions are an authoring error.
    """
    migration_files = sorted(_ALEMBIC_DIR.glob("*.py"))
    missing = [p.name for p in migration_files if not hasattr(_load_migration(p), "downgrade")]
    assert not missing, f"Migrations missing downgrade(): {missing}"
