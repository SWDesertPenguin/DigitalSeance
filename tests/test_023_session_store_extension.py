# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 SessionStore extension tests (T032, T033).

Covers the new ``account_id`` field on :class:`SessionEntry`, the
backwards-compatible legacy create path (token-paste flow keeps
working), the ``_by_account`` reverse index maintenance on create /
delete / TTL expiry, and the FR-011 / clarify Q12 password-change
invalidation primitives (``get_sids_for_account``,
``delete_other_sids_for_account``).
"""

from __future__ import annotations

import asyncio

import pytest

from src.web_ui.session_store import SessionStore

# ---------------------------------------------------------------------------
# Backwards compatibility — legacy token-paste flow still works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_create_leaves_account_id_none() -> None:
    """Existing token-paste callers continue to work; account_id stays None."""
    store = SessionStore()
    sid = await store.create("pid-legacy", "session-legacy", "bearer-legacy")
    entry = await store.get(sid)
    assert entry is not None
    assert entry.participant_id == "pid-legacy"
    assert entry.session_id == "session-legacy"
    assert entry.bearer == "bearer-legacy"
    assert entry.account_id is None


# ---------------------------------------------------------------------------
# Account-id binding on create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_with_account_id_records_binding() -> None:
    """Account-login flow mints an sid with account_id set."""
    store = SessionStore()
    sid = await store.create(account_id="acct-1")
    entry = await store.get(sid)
    assert entry is not None
    assert entry.account_id == "acct-1"
    # account-only state — participant fields remain None until rebind.
    assert entry.participant_id is None
    assert entry.session_id is None
    assert entry.bearer is None


@pytest.mark.asyncio
async def test_create_account_and_participant_state() -> None:
    """A subsequent rebind populates participant fields without losing account_id."""
    store = SessionStore()
    sid = await store.create(
        "pid-1",
        "session-1",
        "bearer-1",
        account_id="acct-1",
    )
    entry = await store.get(sid)
    assert entry is not None
    assert entry.account_id == "acct-1"
    assert entry.participant_id == "pid-1"
    assert entry.session_id == "session-1"
    assert entry.bearer == "bearer-1"


# ---------------------------------------------------------------------------
# Reverse-index maintenance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sids_for_account_returns_active_set() -> None:
    """get_sids_for_account returns every active sid bound to the account."""
    store = SessionStore()
    sid_a = await store.create(account_id="acct-1")
    sid_b = await store.create(account_id="acct-1")
    sid_c = await store.create(account_id="acct-2")
    sids = await store.get_sids_for_account("acct-1")
    assert sids == {sid_a, sid_b}
    assert sid_c not in sids


@pytest.mark.asyncio
async def test_get_sids_for_unknown_account_returns_empty_set() -> None:
    """An unknown account_id yields an empty set, not a KeyError."""
    store = SessionStore()
    assert await store.get_sids_for_account("nope") == set()


@pytest.mark.asyncio
async def test_delete_drops_sid_from_reverse_index() -> None:
    """Deleting a sid removes it from the per-account bucket."""
    store = SessionStore()
    sid_a = await store.create(account_id="acct-1")
    sid_b = await store.create(account_id="acct-1")
    await store.delete(sid_a)
    sids = await store.get_sids_for_account("acct-1")
    assert sids == {sid_b}


@pytest.mark.asyncio
async def test_emptying_a_bucket_drops_the_account_key() -> None:
    """When the last sid for an account is deleted, the bucket itself goes."""
    store = SessionStore()
    sid = await store.create(account_id="acct-1")
    await store.delete(sid)
    # Internal state check: the account_id key is gone, not just an empty set.
    assert "acct-1" not in store._by_account  # noqa: SLF001


@pytest.mark.asyncio
async def test_legacy_delete_does_not_touch_reverse_index() -> None:
    """Deleting a legacy (account_id=None) sid leaves the reverse index alone."""
    store = SessionStore()
    legacy_sid = await store.create("pid", "ses", "bearer")
    account_sid = await store.create(account_id="acct-1")
    await store.delete(legacy_sid)
    # The acct-1 binding survives.
    assert await store.get_sids_for_account("acct-1") == {account_sid}


# ---------------------------------------------------------------------------
# FR-011 / clarify Q12 — password-change invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_other_sids_preserves_actor_sid() -> None:
    """The actor's sid survives; every other sid for the account is dropped."""
    store = SessionStore()
    actor_sid = await store.create(account_id="acct-1")
    other_a = await store.create(account_id="acct-1")
    other_b = await store.create(account_id="acct-1")
    dropped = await store.delete_other_sids_for_account(
        "acct-1",
        except_sid=actor_sid,
    )
    assert dropped == 2
    sids = await store.get_sids_for_account("acct-1")
    assert sids == {actor_sid}
    # Confirm the others are actually gone.
    assert await store.get(other_a) is None
    assert await store.get(other_b) is None
    # Actor still resolves.
    assert await store.get(actor_sid) is not None


@pytest.mark.asyncio
async def test_delete_other_sids_does_not_affect_other_accounts() -> None:
    """Other accounts' sids are untouched."""
    store = SessionStore()
    actor_sid = await store.create(account_id="acct-1")
    sibling = await store.create(account_id="acct-1")
    other_account = await store.create(account_id="acct-2")
    await store.delete_other_sids_for_account("acct-1", except_sid=actor_sid)
    # acct-2's sid still resolves.
    assert await store.get(other_account) is not None
    # Sibling sid is gone.
    assert await store.get(sibling) is None


@pytest.mark.asyncio
async def test_delete_other_sids_for_unknown_account_is_noop() -> None:
    """Unknown account_id returns 0 dropped, no exception."""
    store = SessionStore()
    dropped = await store.delete_other_sids_for_account("nope", except_sid="ignored")
    assert dropped == 0


# ---------------------------------------------------------------------------
# TTL expiry path also cleans the reverse index
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_expired_drops_from_reverse_index() -> None:
    """Expired sids are dropped from both the primary dict and the reverse index."""
    store = SessionStore(ttl_seconds=0)  # Everything is immediately expired.
    sid = await store.create(account_id="acct-1")
    # Yield once so the monotonic-clock gap is non-zero.
    await asyncio.sleep(0.01)
    purged = await store.purge_expired()
    assert purged == 1
    assert await store.get(sid) is None
    assert await store.get_sids_for_account("acct-1") == set()
