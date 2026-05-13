# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 cross-instance broadcast unit tests (T013 of tasks.md).

Covers ``src/web_ui/cross_instance_broadcast.py`` at the unit level:

- Same-instance fast path: in-process broadcast fires regardless of
  whether a pool is provided (single-instance deployment stays correct).
- Cross-instance path: NOTIFY is emitted with the correct channel name
  and serialized envelope when a pool is supplied.
- Failure isolation: NOTIFY errors must not block the in-process
  broadcast (FR-017 fail-soft contract carries through to cross-instance).
- Payload-size cap: envelopes that exceed the 7000-byte NOTIFY limit
  log a warning and SKIP the NOTIFY rather than letting Postgres
  truncate.
- Snippet truncation: trigger snippets longer than
  ``SNIPPET_NOTIFY_CHAR_LIMIT`` (1000 chars) are truncated in the
  envelope before broadcast; ``trigger_snippet_truncated`` flag is set.
- LISTEN handler: malformed JSON payloads are logged at WARN and do
  NOT raise; well-formed payloads rebroadcast verbatim.

Two-process e2e fixture (full SC-010 verification) lives at T044 with
the ``@pytest.mark.requires_postgres`` marker.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.web_ui import cross_instance_broadcast as cib


def _make_envelope(snippet: str | None = None) -> dict:
    """Build a detection_event_appended envelope for the broadcast helpers."""
    return {
        "v": 1,
        "type": "detection_event_appended",
        "event": {
            "event_id": 42,
            "event_class": "ai_question_opened",
            "event_class_label": "AI question opened",
            "participant_id": "p1",
            "trigger_snippet": snippet,
            "detector_score": 0.87,
            "turn_number": 14,
            "timestamp": "2026-05-11T14:32:01.234Z",
            "disposition": "pending",
        },
    }


# ---------------------------------------------------------------------------
# Same-instance fast path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_session_event_in_process_only_when_no_pool() -> None:
    """Same-instance path: broadcast fires; NOTIFY skipped without a pool."""
    envelope = _make_envelope("hello")
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()) as mock_bcast:
        await cib.broadcast_session_event("s1", envelope, pool=None)
    mock_bcast.assert_awaited_once()
    args, kwargs = mock_bcast.await_args
    assert args[0] == "s1"
    assert kwargs.get("allow_roles") == cib.FACILITATOR_ROLES


@pytest.mark.asyncio
async def test_broadcast_session_event_runs_in_process_before_notify() -> None:
    """In-process broadcast fires even when NOTIFY raises (fail-soft)."""
    pool = MagicMock()

    class _FailingAcquire:
        def __aenter__(self):  # noqa: D401
            return self  # not awaited; raise on execute below

        async def __aexit__(self, *_args):  # noqa: D401
            return False

        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("notify failed")

    pool.acquire = MagicMock(return_value=_FailingAcquire())

    envelope = _make_envelope("hello")
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()) as mock_bcast:
        await cib.broadcast_session_event("s1", envelope, pool=pool)
    mock_bcast.assert_awaited_once()


# ---------------------------------------------------------------------------
# Cross-instance NOTIFY path
# ---------------------------------------------------------------------------


class _FakeConn:
    """Captures the NOTIFY SQL fragment emitted by ``_emit_notify``."""

    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, sql: str) -> None:
        self.executed.append(sql)


class _FakePool:
    """Async-context-manager pool wrapper exposing one ``_FakeConn``."""

    def __init__(self) -> None:
        self.conn = _FakeConn()

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_inner):  # noqa: D401, N805
                return pool.conn

            async def __aexit__(self_inner, *_args):  # noqa: D401, N805
                return False

        return _Ctx()


@pytest.mark.asyncio
async def test_broadcast_emits_notify_with_channel_and_payload() -> None:
    """NOTIFY targets ``detection_events_<session>`` with serialized envelope."""
    pool = _FakePool()
    envelope = _make_envelope("hello")
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()):
        await cib.broadcast_session_event("s1", envelope, pool=pool)
    assert pool.conn.executed, "NOTIFY MUST be emitted on the per-session channel"
    sql = pool.conn.executed[0]
    assert sql.startswith("NOTIFY detection_events_s1, '"), sql
    # Round-trip JSON inside the literal: strip the SQL wrapping then parse.
    body = sql[len("NOTIFY detection_events_s1, '") : -1]
    # Postgres-escape '' was applied; reverse it before JSON decode.
    decoded = json.loads(body.replace("''", "'"))
    assert decoded["type"] == "detection_event_appended"
    assert decoded["event"]["event_id"] == 42


@pytest.mark.asyncio
async def test_broadcast_skips_notify_when_payload_over_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Envelopes over the 7000-byte cap MUST log + skip rather than truncate."""
    pool = _FakePool()
    # Build a huge envelope by bypassing the snippet truncation cap (sit it on
    # a non-snippet field so ``_truncate_snippet`` does not trim it).
    envelope = _make_envelope("ok")
    envelope["bulk"] = "X" * 10_000
    caplog.set_level("WARNING", logger="src.web_ui.cross_instance_broadcast")
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()):
        await cib.broadcast_session_event("s1", envelope, pool=pool)
    assert pool.conn.executed == [], "NOTIFY MUST NOT fire when over the byte cap"
    assert any(
        "payload_over_limit" in record.message
        or getattr(record, "bytes", 0) > cib.NOTIFY_PAYLOAD_BYTE_LIMIT
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# Snippet truncation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_envelope_snippet_truncated_in_place() -> None:
    """Snippets over ``SNIPPET_NOTIFY_CHAR_LIMIT`` are trimmed before broadcast."""
    long_snippet = "A" * (cib.SNIPPET_NOTIFY_CHAR_LIMIT + 200)
    envelope = _make_envelope(long_snippet)
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()) as mock_bcast:
        await cib.broadcast_session_event("s1", envelope, pool=None)
    sent_envelope = mock_bcast.await_args.args[1]
    assert len(sent_envelope["event"]["trigger_snippet"]) == cib.SNIPPET_NOTIFY_CHAR_LIMIT
    assert sent_envelope["event"]["trigger_snippet_truncated"] is True


@pytest.mark.asyncio
async def test_envelope_short_snippet_marks_untruncated() -> None:
    """Short snippets pass through with ``trigger_snippet_truncated=False``."""
    envelope = _make_envelope("brief")
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()) as mock_bcast:
        await cib.broadcast_session_event("s1", envelope, pool=None)
    sent_envelope = mock_bcast.await_args.args[1]
    assert sent_envelope["event"]["trigger_snippet"] == "brief"
    assert sent_envelope["event"]["trigger_snippet_truncated"] is False


# ---------------------------------------------------------------------------
# Channel-name helper
# ---------------------------------------------------------------------------


def test_channel_for_session_uses_per_session_prefix() -> None:
    """Channel naming is deterministic per session for the LISTEN side."""
    assert cib._channel_for_session("abc") == "detection_events_abc"
    assert cib._channel_for_session("with-dashes") == "detection_events_with-dashes"


# ---------------------------------------------------------------------------
# LISTEN handler payload parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listen_callback_rebroadcasts_well_formed_payload() -> None:
    """The on-NOTIFY callback parses JSON + rebroadcasts to local subscribers."""
    fake_conn = SimpleNamespace(add_listener=AsyncMock())
    pool = MagicMock()
    pool.acquire = AsyncMock(return_value=fake_conn)
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()):
        await cib.listen_for_session_events(pool, "s1")
    fake_conn.add_listener.assert_awaited_once()
    args, _ = fake_conn.add_listener.await_args
    channel, callback = args
    assert channel == "detection_events_s1"
    # Invoke the callback with a well-formed payload — no exception, broadcast called.
    payload = json.dumps(_make_envelope("hi"))
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()) as mock_bcast:
        await callback(None, 0, channel, payload)
    mock_bcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_listen_callback_swallows_malformed_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed JSON logs WARN, does NOT raise, does NOT rebroadcast."""
    fake_conn = SimpleNamespace(add_listener=AsyncMock())
    pool = MagicMock()
    pool.acquire = AsyncMock(return_value=fake_conn)
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()):
        await cib.listen_for_session_events(pool, "s1")
    _, callback = fake_conn.add_listener.await_args.args
    caplog.set_level("WARNING", logger="src.web_ui.cross_instance_broadcast")
    with patch.object(cib, "broadcast_to_session_roles", new=AsyncMock()) as mock_bcast:
        await callback(None, 0, "detection_events_s1", "{not json")
    mock_bcast.assert_not_awaited()
    assert any("malformed_notify" in r.message for r in caplog.records)
