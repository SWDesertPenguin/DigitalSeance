# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 register-state repository.

Backs spec 021 US2 / US3 — session-level register slider and per-participant
override. Two tables (alembic 013): ``session_register`` (one row per
session, the facilitator-set slider value 1-5) and
``participant_register_override`` (zero-or-one row per participant, the
override slider value 1-5). Both cascade-delete on session removal; the
override also cascades on participant removal per FR-015 / SC-007.

The resolver (`resolve_register`) walks the override → session → default
chain in a single SQL query with two LEFT JOINs and a COALESCE, returning
the effective ``(slider, RegisterPreset, source)`` tuple per
research.md §5. ``source`` is the two-value enum ``"session"`` /
``"participant_override"`` per FR-010 — when neither row exists the
session-default fallback is reported as ``"session"`` because the slider's
default IS the session-level state in the absence of an explicit set.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import asyncpg

from src.prompts.register_presets import REGISTER_PRESETS, RegisterPreset, preset_for_slider
from src.repositories.base import BaseRepository

RegisterSource = Literal["session", "participant_override"]


@dataclass(frozen=True)
class SessionRegister:
    """One ``session_register`` row — facilitator-set slider for a session."""

    session_id: str
    slider_value: int
    set_by_facilitator_id: str
    last_changed_at: datetime

    @classmethod
    def from_record(cls, record: asyncpg.Record) -> SessionRegister:
        return cls(
            session_id=record["session_id"],
            slider_value=int(record["slider_value"]),
            set_by_facilitator_id=record["set_by_facilitator_id"],
            last_changed_at=record["last_changed_at"],
        )


@dataclass(frozen=True)
class ParticipantRegisterOverride:
    """One ``participant_register_override`` row — facilitator-set override.

    Override scope is a single participant. Cascades on participant or
    session delete (FR-015 / SC-007); explicit clear is a DELETE that
    emits ``participant_register_override_cleared``.
    """

    participant_id: str
    session_id: str
    slider_value: int
    set_by_facilitator_id: str
    last_changed_at: datetime

    @classmethod
    def from_record(cls, record: asyncpg.Record) -> ParticipantRegisterOverride:
        return cls(
            participant_id=record["participant_id"],
            session_id=record["session_id"],
            slider_value=int(record["slider_value"]),
            set_by_facilitator_id=record["set_by_facilitator_id"],
            last_changed_at=record["last_changed_at"],
        )


def register_default_from_env() -> int:
    """Read ``SACP_REGISTER_DEFAULT`` with a fallback to ``2`` (Conversational).

    The validator (T004) ensures any set value parses as int in {1..5} at
    startup. Runtime drift (an empty value, a failed parse) lands here and
    falls back to ``2`` per FR-009 + spec V16 default.
    """
    raw = os.environ.get("SACP_REGISTER_DEFAULT")
    if raw is None or raw.strip() == "":
        return 2
    try:
        candidate = int(raw)
    except ValueError:
        return 2
    if 1 <= candidate <= 5:
        return candidate
    return 2


class RegisterRepository(BaseRepository):
    """Data access for session-level register and per-participant override.

    The two tables live in the same repository because the resolver needs
    both in one SQL query (research.md §5: a single LEFT JOIN chain over
    override → session → default beats two round-trips). Lifecycle
    operations (set, update, clear, list) are split across method names
    keyed to the audit-event taxonomy (`session_register_changed`,
    `participant_register_override_set`, `_cleared`).
    """

    # ------------------------------------------------------------------
    # session_register CRUD (T038)
    # ------------------------------------------------------------------

    async def get_session_register(
        self,
        session_id: str,
    ) -> SessionRegister | None:
        """Return the ``session_register`` row for a session, or None.

        Absence MUST be reported as ``None`` so the resolver falls through
        to the env default per FR-009. The row is created on first
        facilitator slider-set; subsequent sets UPDATE in place.
        """
        record = await self._fetch_one(
            "SELECT * FROM session_register WHERE session_id = $1",
            session_id,
        )
        return SessionRegister.from_record(record) if record else None

    async def upsert_session_register(
        self,
        *,
        session_id: str,
        slider_value: int,
        facilitator_id: str,
    ) -> tuple[SessionRegister, SessionRegister | None]:
        """INSERT-or-UPDATE the session_register row; return (new, previous).

        Returns the new row PLUS the previous-state row (or ``None`` if
        the row was created by this call). The caller uses the
        previous-state row to populate the audit event's ``previous_value``
        per ``contracts/audit-events.md §session_register_changed``.

        Idempotent semantics per FR-008's "submit a slider value equal
        to the existing value" clarification: the row IS updated
        (`last_changed_at` advances) and the audit row IS emitted (the
        operator's intent to confirm the value is itself an audit-relevant
        event). Caller-side logic owns the audit-emit after this call.
        """
        if not 1 <= slider_value <= 5:
            msg = f"slider_value must be in [1, 5]; got {slider_value}"
            raise ValueError(msg)
        previous = await self.get_session_register(session_id)
        record = await self._fetch_one(
            """
            INSERT INTO session_register
                (session_id, slider_value, set_by_facilitator_id, last_changed_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (session_id) DO UPDATE
                SET slider_value = EXCLUDED.slider_value,
                    set_by_facilitator_id = EXCLUDED.set_by_facilitator_id,
                    last_changed_at = NOW()
            RETURNING *
            """,
            session_id,
            slider_value,
            facilitator_id,
        )
        # _fetch_one returns Record | None but RETURNING * always emits a row.
        if record is None:
            msg = "session_register upsert returned no row"
            raise RuntimeError(msg)
        return SessionRegister.from_record(record), previous

    # ------------------------------------------------------------------
    # participant_register_override CRUD (T050)
    # ------------------------------------------------------------------

    async def get_participant_override(
        self,
        participant_id: str,
    ) -> ParticipantRegisterOverride | None:
        """Return the override row for a participant, or None."""
        record = await self._fetch_one(
            "SELECT * FROM participant_register_override WHERE participant_id = $1",
            participant_id,
        )
        return ParticipantRegisterOverride.from_record(record) if record else None

    async def upsert_participant_override(
        self,
        *,
        participant_id: str,
        session_id: str,
        slider_value: int,
        facilitator_id: str,
    ) -> tuple[ParticipantRegisterOverride, ParticipantRegisterOverride | None]:
        """INSERT-or-UPDATE override row; return (new, previous).

        Same idempotent semantics as ``upsert_session_register`` — even a
        no-op set bumps ``last_changed_at`` and emits an audit event.
        """
        if not 1 <= slider_value <= 5:
            msg = f"slider_value must be in [1, 5]; got {slider_value}"
            raise ValueError(msg)
        previous = await self.get_participant_override(participant_id)
        record = await self._fetch_one(
            """
            INSERT INTO participant_register_override
                (participant_id, session_id, slider_value,
                 set_by_facilitator_id, last_changed_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (participant_id) DO UPDATE
                SET slider_value = EXCLUDED.slider_value,
                    set_by_facilitator_id = EXCLUDED.set_by_facilitator_id,
                    last_changed_at = NOW()
            RETURNING *
            """,
            participant_id,
            session_id,
            slider_value,
            facilitator_id,
        )
        if record is None:
            msg = "participant_register_override upsert returned no row"
            raise RuntimeError(msg)
        return ParticipantRegisterOverride.from_record(record), previous

    async def clear_participant_override(
        self,
        participant_id: str,
    ) -> ParticipantRegisterOverride | None:
        """Explicit DELETE — returns the cleared row or None if absent.

        Cascade-deletes (participant or session removed) do NOT route
        through this method per FR-015 + research.md §8 — the parent
        delete event suffices and no
        ``participant_register_override_cleared`` audit row is emitted in
        that case.
        """
        previous = await self.get_participant_override(participant_id)
        if previous is None:
            return None
        await self._execute(
            "DELETE FROM participant_register_override WHERE participant_id = $1",
            participant_id,
        )
        return previous

    # ------------------------------------------------------------------
    # Resolver — override → session → default (T039 + T051)
    # ------------------------------------------------------------------

    async def resolve_register(
        self,
        *,
        participant_id: str,
        session_id: str,
        register_default: int | None = None,
    ) -> tuple[int, RegisterPreset, RegisterSource]:
        """Resolve the participant's effective register per research.md §5.

        Override wins iff its row exists; otherwise the source is
        ``"session"`` regardless of whether a session_register row
        exists or the env default applies (FR-010 two-value enum).
        """
        default_value = (
            register_default if register_default is not None else register_default_from_env()
        )
        record = await self._fetch_one(_RESOLVE_REGISTER_SQL, participant_id, session_id)
        if record is not None and record["override_slider"] is not None:
            slider = int(record["override_slider"])
            return slider, preset_for_slider(slider), "participant_override"
        if record is not None and record["session_slider"] is not None:
            slider = int(record["session_slider"])
            return slider, preset_for_slider(slider), "session"
        return default_value, preset_for_slider(default_value), "session"


_RESOLVE_REGISTER_SQL = """
    SELECT
        pro.slider_value AS override_slider,
        ses.slider_value AS session_slider
    FROM (SELECT $1::TEXT AS pid, $2::TEXT AS sid) AS args
    LEFT JOIN participant_register_override pro
        ON pro.participant_id = args.pid
    LEFT JOIN session_register ses
        ON ses.session_id = args.sid
"""


__all__ = [
    "REGISTER_PRESETS",  # re-export for callers that want one import
    "ParticipantRegisterOverride",
    "RegisterRepository",
    "RegisterSource",
    "SessionRegister",
    "register_default_from_env",
]
