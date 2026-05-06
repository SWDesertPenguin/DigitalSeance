"""Per-session batch scheduler (spec 013 mechanism 1 / US1).

Hosts ``BatchEnvelope`` and the per-session flush task that coalesces
AI-to-human messages on the configured cadence. Spawned in the
``loop.py`` session-init path when ``HighTrafficSessionConfig.batch_cadence_s``
is set.

State-change events (convergence, session-state transitions, participant
updates, etc.) MUST bypass envelopes and emit immediately per FR-004.
The enqueue path is for ``message`` events only.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Hard-close slack on top of the configured cadence (spec 013 FR-003 / SC-002).
_SLACK_S = 5.0

log = logging.getLogger(__name__)


@dataclass
class BatchEnvelope:
    """One open envelope for a (session_id, recipient_id) pair."""

    session_id: str
    recipient_id: str
    opened_at: datetime
    scheduled_close_at: datetime
    source_turn_ids: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    open_monotonic: float = 0.0  # for routing_log P95 capture


class BatchScheduler:
    """Process-wide scheduler holding per-session flush tasks.

    Lazy-spawns a flush coroutine per session on first enqueue. Cancels
    all outstanding tasks on ``stop()``. The cadence and slack are
    captured from the high-traffic config at construction time.
    """

    def __init__(self, *, cadence_s: int, broadcast: Any | None = None) -> None:
        self._cadence_s = float(cadence_s)
        self._slack_s = _SLACK_S
        self._envelopes: dict[tuple[str, str], BatchEnvelope] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._broadcast = broadcast  # injection point — defaults to broadcast_to_session
        self._stopped = False

    def enqueue(
        self,
        *,
        session_id: str,
        recipient_id: str,
        source_turn_id: str,
        message: dict[str, Any],
    ) -> None:
        """Append a message to the (session, recipient) envelope; spawn flush task if needed."""
        if self._stopped:
            return
        key = (session_id, recipient_id)
        envelope = self._envelopes.get(key)
        if envelope is None:
            envelope = self._open_envelope(session_id, recipient_id)
            self._envelopes[key] = envelope
        envelope.source_turn_ids.append(source_turn_id)
        envelope.messages.append(message)
        if session_id not in self._tasks:
            self._tasks[session_id] = asyncio.create_task(self._session_flush_loop(session_id))

    def _open_envelope(self, session_id: str, recipient_id: str) -> BatchEnvelope:
        now = datetime.now(UTC)
        return BatchEnvelope(
            session_id=session_id,
            recipient_id=recipient_id,
            opened_at=now,
            scheduled_close_at=now,  # set on first flush wake; placeholder
            open_monotonic=time.monotonic(),
        )

    async def _session_flush_loop(self, session_id: str) -> None:
        """Tick once per cadence, flushing all open envelopes for this session."""
        try:
            while not self._stopped:
                await asyncio.sleep(self._cadence_s)
                await self._flush_session(session_id)
        except asyncio.CancelledError:
            await self._flush_session(session_id)
            raise

    async def _flush_session(self, session_id: str) -> None:
        keys = [k for k in self._envelopes if k[0] == session_id]
        for key in keys:
            envelope = self._envelopes.pop(key, None)
            if envelope is None or not envelope.messages:
                continue
            await self._emit(envelope)

    async def _emit(self, envelope: BatchEnvelope) -> None:
        elapsed_s = time.monotonic() - envelope.open_monotonic
        if elapsed_s > self._cadence_s + self._slack_s:
            log.warning(
                "batch_envelope_slack_breach: session=%s recipient=%s elapsed=%.2fs budget=%.2fs",
                envelope.session_id,
                envelope.recipient_id,
                elapsed_s,
                self._cadence_s + self._slack_s,
            )
        if self._broadcast is None:
            return  # tests may inject a no-op
        from src.web_ui.events import batch_envelope_event

        event = batch_envelope_event(envelope)
        await self._broadcast(envelope.session_id, event)

    async def stop(self) -> None:
        """Cancel all per-session flush tasks; flushes any remaining open envelopes."""
        self._stopped = True
        for task in list(self._tasks.values()):
            task.cancel()
        for task in list(self._tasks.values()):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
