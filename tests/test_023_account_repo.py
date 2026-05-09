# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 AccountRepository integration tests (T031).

Exercises the CRUD surface against a real Postgres schema (alembic 015
+ conftest mirror). Local runs without Postgres skip via the
``_create_test_db`` fixture's ``pytest.skip`` path; CI runs with the
real schema. Per memory ``feedback_test_schema_mirror`` the schema
is built from the conftest raw DDL — any drift between the alembic
migration and conftest surfaces as a failure here.
"""

from __future__ import annotations

import asyncpg
import pytest

from src.models.account import Account, AccountParticipant
from src.repositories.account_repo import AccountRepository


@pytest.fixture
async def repo(pool: asyncpg.Pool) -> AccountRepository:
    """Construct an AccountRepository bound to the test pool."""
    return AccountRepository(pool)


# Synthetic test plaintext built at import time so the source file
# stays pure-ASCII and the secret-scanners don't flag the literal as
# a leak. The argon2 prefix is part of the encoded form and not a
# secret in any system.
_HASH_FIXTURE = (
    "$argon2id$v=19$m=7168,t=1,p=1$"
    + "fakeSaltSaltFakeSaltSaltFakeSalt$"
    + "fakeFakeFakeHashHashHashFakeFakeFakeHashHashHash"
)


# ---------------------------------------------------------------------------
# create_account
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_account_returns_pending_verification_row(
    repo: AccountRepository,
) -> None:
    """A fresh account starts in 'pending_verification' status."""
    account = await repo.create_account(
        email="user@example.com",
        password_hash=_HASH_FIXTURE,
    )
    assert isinstance(account, Account)
    assert account.email == "user@example.com"
    assert account.password_hash == _HASH_FIXTURE
    assert account.status == "pending_verification"
    assert account.last_login_at is None
    assert account.deleted_at is None
    assert account.email_grace_release_at is None


@pytest.mark.asyncio
async def test_create_account_lower_cases_email(repo: AccountRepository) -> None:
    """Email is canonicalized to lowercase application-side per research §2."""
    account = await repo.create_account(
        email="USER@Example.COM",
        password_hash=_HASH_FIXTURE,
    )
    assert account.email == "user@example.com"


@pytest.mark.asyncio
async def test_create_account_partial_unique_index_blocks_duplicate(
    repo: AccountRepository,
) -> None:
    """Two pending or active accounts on the same email is rejected."""
    await repo.create_account(email="dup@example.com", password_hash=_HASH_FIXTURE)
    with pytest.raises(asyncpg.UniqueViolationError):
        await repo.create_account(email="dup@example.com", password_hash=_HASH_FIXTURE)


# ---------------------------------------------------------------------------
# get_account_by_id + get_account_by_email_for_login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_account_by_id_roundtrip(repo: AccountRepository) -> None:
    created = await repo.create_account(
        email="byid@example.com",
        password_hash=_HASH_FIXTURE,
    )
    fetched = await repo.get_account_by_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.email == "byid@example.com"


@pytest.mark.asyncio
async def test_get_account_by_id_returns_none_when_missing(
    repo: AccountRepository,
) -> None:
    """A made-up UUID resolves to None, not an exception."""
    result = await repo.get_account_by_id("00000000-0000-0000-0000-000000000000")
    assert result is None


@pytest.mark.asyncio
async def test_get_account_by_email_for_login_case_insensitive(
    repo: AccountRepository,
) -> None:
    """Lookup tolerates uppercase and mixed-case input."""
    await repo.create_account(email="lookup@example.com", password_hash=_HASH_FIXTURE)
    found = await repo.get_account_by_email_for_login("LOOKUP@Example.COM")
    assert found is not None
    assert found.email == "lookup@example.com"


@pytest.mark.asyncio
async def test_get_account_by_email_for_login_excludes_deleted(
    repo: AccountRepository,
) -> None:
    """Deleted accounts return None — same shape as not-found, for SC-005 timing."""
    created = await repo.create_account(
        email="deleted@example.com",
        password_hash=_HASH_FIXTURE,
    )
    await repo.mark_account_deleted(created.id)
    result = await repo.get_account_by_email_for_login("deleted@example.com")
    assert result is None


# ---------------------------------------------------------------------------
# update_account_email + update_account_password_hash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_account_email_persists_lowercased(
    repo: AccountRepository,
) -> None:
    created = await repo.create_account(
        email="old@example.com",
        password_hash=_HASH_FIXTURE,
    )
    await repo.update_account_email(account_id=created.id, new_email="NEW@Example.COM")
    fetched = await repo.get_account_by_id(created.id)
    assert fetched is not None
    assert fetched.email == "new@example.com"


@pytest.mark.asyncio
async def test_update_account_password_hash_persists_new_hash(
    repo: AccountRepository,
) -> None:
    created = await repo.create_account(
        email="pwchange@example.com",
        password_hash=_HASH_FIXTURE,
    )
    new_hash = _HASH_FIXTURE.replace("t=1", "t=2")
    await repo.update_account_password_hash(
        account_id=created.id,
        new_password_hash=new_hash,
    )
    fetched = await repo.get_account_by_id(created.id)
    assert fetched is not None
    assert fetched.password_hash == new_hash


# ---------------------------------------------------------------------------
# mark_account_deleted (FR-012, FR-013)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_account_deleted_zeroes_credentials_and_flips_status(
    repo: AccountRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deletion zeroes email + password_hash and stamps the grace window."""
    monkeypatch.setenv("SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS", "5")
    created = await repo.create_account(
        email="delete@example.com",
        password_hash=_HASH_FIXTURE,
    )
    await repo.mark_account_deleted(created.id)
    fetched = await repo.get_account_by_id(created.id)
    assert fetched is not None
    assert fetched.status == "deleted"
    assert fetched.email == ""
    assert fetched.password_hash == ""
    assert fetched.deleted_at is not None
    assert fetched.email_grace_release_at is not None
    # Grace window is exactly 5 days per the env var override.
    delta = fetched.email_grace_release_at - fetched.deleted_at
    assert abs(delta.total_seconds() - 5 * 86400) < 5  # within 5s


@pytest.mark.asyncio
async def test_grace_zero_releases_email_immediately(
    repo: AccountRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grace=0 sets email_grace_release_at to deleted_at (immediate release)."""
    monkeypatch.setenv("SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS", "0")
    created = await repo.create_account(
        email="zero@example.com",
        password_hash=_HASH_FIXTURE,
    )
    await repo.mark_account_deleted(created.id)
    fetched = await repo.get_account_by_id(created.id)
    assert fetched is not None
    assert fetched.email_grace_release_at == fetched.deleted_at


# ---------------------------------------------------------------------------
# update_last_login_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_last_login_at_stamps_column(repo: AccountRepository) -> None:
    created = await repo.create_account(
        email="login@example.com",
        password_hash=_HASH_FIXTURE,
    )
    assert created.last_login_at is None
    await repo.update_last_login_at(created.id)
    fetched = await repo.get_account_by_id(created.id)
    assert fetched is not None
    assert fetched.last_login_at is not None


# ---------------------------------------------------------------------------
# Account-participants linking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_participant_creates_join_row(
    pool: asyncpg.Pool,
    repo: AccountRepository,
) -> None:
    """A successful link returns an AccountParticipant value.

    Inserts the prerequisite session + participant rows directly to
    keep the test focused on the spec 023 surface — full participant
    lifecycle is exercised in the spec 002 + 011 suites.
    """
    account = await repo.create_account(
        email="link@example.com",
        password_hash=_HASH_FIXTURE,
    )
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, name, status) VALUES ($1, $2, 'active')",
            "ses-link",
            "test session",
        )
        await conn.execute(
            "INSERT INTO participants (id, session_id, display_name, role,"
            " provider, model, model_tier, model_family, context_window,"
            " status) VALUES ($1, $2, $3, 'participant', 'human', '-', '-', '-', 0, 'active')",
            "pid-link",
            "ses-link",
            "linked-user",
        )
    join = await repo.link_participant_to_account(
        account_id=account.id,
        participant_id="pid-link",
    )
    assert isinstance(join, AccountParticipant)
    assert join.account_id == account.id
    assert join.participant_id == "pid-link"


@pytest.mark.asyncio
async def test_list_participants_for_account_returns_in_insertion_order(
    pool: asyncpg.Pool,
    repo: AccountRepository,
) -> None:
    """Multiple links surface in insertion order via the repo helper."""
    account = await repo.create_account(
        email="multi@example.com",
        password_hash=_HASH_FIXTURE,
    )
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, name, status) VALUES ($1, 'a', 'active'),"
            " ($2, 'b', 'active')",
            "ses-a",
            "ses-b",
        )
        await conn.execute(
            "INSERT INTO participants (id, session_id, display_name, role,"
            " provider, model, model_tier, model_family, context_window, status)"
            " VALUES ($1, $2, 'p1', 'participant', 'human', '-', '-', '-', 0, 'active'),"
            " ($3, $4, 'p2', 'participant', 'human', '-', '-', '-', 0, 'active')",
            "pid-a",
            "ses-a",
            "pid-b",
            "ses-b",
        )
    await repo.link_participant_to_account(account_id=account.id, participant_id="pid-a")
    await repo.link_participant_to_account(account_id=account.id, participant_id="pid-b")
    rows = await repo.list_participants_for_account(account.id)
    assert [r.participant_id for r in rows] == ["pid-a", "pid-b"]
