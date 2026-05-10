# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 Phase 5 (US3) acceptance scenarios T044-T049.

Exercises per-participant register overrides through the
``RegisterRepository``, the ``log_register_change`` audit helper for
the override-set / override-cleared distinction, the resolver's
override-vs-session priority, and the cascade-on-delete contract per
FR-015 / SC-007.

Each test maps 1:1 to a scenario in
[spec.md User Story 3 "Acceptance Scenarios"](../specs/021-ai-response-shaping/spec.md):

  - T044 -> Scenario 1: override set -> source='participant_override';
    override_set audit row written.
  - T045 -> Scenario 2 (covers SC-005): override scoping --
    other participants in the same session unaffected.
  - T046 -> Scenario 3: override-targeted preset text differs from the
    session-level preset's text.
  - T047 -> Scenario 4: pause-resume idempotency.
  - T048 -> Scenario 5 (covers SC-007 cascade-on-participant).
  - T049 -> Cascade test 2 (covers SC-007 cascade-on-session): no
    ``participant_register_override_cleared`` audit row emitted.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from src.repositories.log_repo import LogRepository
from src.repositories.register_repo import RegisterRepository

if TYPE_CHECKING:
    import asyncpg

pytestmark = pytest.mark.asyncio


async def _make_session(
    pool: asyncpg.Pool,
    *,
    extra_participants: int,
) -> tuple[str, str, list[str]]:
    """Build a session, return (session_id, facilitator_id, [extra_pids])."""
    from src.repositories.session_repo import SessionRepository

    session, facilitator, _ = await SessionRepository(pool).create_session(
        "Override Test Session",
        facilitator_display_name="Facilitator",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )
    extra = await _seed_participants(pool, session.id, extra_participants)
    return session.id, facilitator.id, extra


async def _seed_participants(
    pool: asyncpg.Pool,
    session_id: str,
    count: int,
) -> list[str]:
    """Seed ``count`` AI participants and return their IDs."""
    from cryptography.fernet import Fernet

    from src.repositories.participant_repo import ParticipantRepository

    p_repo = ParticipantRepository(pool, encryption_key=Fernet.generate_key().decode())
    extras: list[str] = []
    for index in range(count):
        participant, _ = await p_repo.add_participant(
            session_id=session_id,
            display_name=f"Speaker-{index}",
            provider="anthropic",
            model="claude-sonnet-4-6",
            model_tier="high",
            model_family="anthropic",
            context_window=200000,
            api_key="test-api-key",
            auth_token=f"tok-{session_id[:6]}-{index}",
            auto_approve=True,
        )
        extras.append(participant.id)
    return extras


async def _set_session_slider(pool: asyncpg.Pool, session_id: str, fid: str, slider: int) -> None:
    """Set the session-level register slider."""
    await RegisterRepository(pool).upsert_session_register(
        session_id=session_id, slider_value=slider, facilitator_id=fid
    )


async def _set_override(
    pool: asyncpg.Pool,
    *,
    target_id: str,
    session_id: str,
    fid: str,
    slider: int,
) -> tuple[object, object]:
    """Upsert override; returns ``(new, previous)``."""
    return await RegisterRepository(pool).upsert_participant_override(
        participant_id=target_id, session_id=session_id, slider_value=slider, facilitator_id=fid
    )


async def _emit_override_set_audit(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    target_id: str,
    fid: str,
    new_slider: int,
    preset_name: str,
    session_slider_at_time: int | None,
) -> None:
    """Write the override-set audit row through the helper."""
    await LogRepository(pool).log_register_change(
        action="participant_register_override_set",
        session_id=session_id,
        target_id=target_id,
        previous_value=None,
        new_value={
            "slider_value": new_slider,
            "preset": preset_name,
            "session_slider_at_time": session_slider_at_time,
        },
        facilitator_id=fid,
    )


def _filter_action(rows: list, action: str) -> list:
    return [row for row in rows if row.action == action]


# ---------------------------------------------------------------------------
# T044: override set -> source='participant_override' + audit row.
# ---------------------------------------------------------------------------


async def test_t044_override_set_writes_audit_and_changes_source(pool: asyncpg.Pool) -> None:
    """Setting an override flips the resolver's source and emits an audit row."""
    session_id, fid, extras = await _make_session(pool, extra_participants=1)
    target_id = extras[0]
    await _set_session_slider(pool, session_id, fid, slider=2)
    new_row, previous = await _set_override(
        pool, target_id=target_id, session_id=session_id, fid=fid, slider=5
    )
    assert previous is None and new_row.slider_value == 5
    await _emit_override_set_audit(
        pool,
        session_id=session_id,
        target_id=target_id,
        fid=fid,
        new_slider=5,
        preset_name="academic",
        session_slider_at_time=2,
    )
    slider, preset, source = await RegisterRepository(pool).resolve_register(
        participant_id=target_id, session_id=session_id
    )
    assert (slider, preset.name, source) == (5, "academic", "participant_override")
    audits = _filter_action(
        await LogRepository(pool).get_audit_log(session_id), "participant_register_override_set"
    )
    assert len(audits) == 1
    assert json.loads(audits[0].new_value)["session_slider_at_time"] == 2


# ---------------------------------------------------------------------------
# T045: override scoping -- other participants stay on session-level preset.
# ---------------------------------------------------------------------------


async def test_t045_override_does_not_affect_other_participants(pool: asyncpg.Pool) -> None:
    """An override on one participant leaves siblings on register_source='session'."""
    session_id, fid, extras = await _make_session(pool, extra_participants=3)
    target_id, sibling_a, sibling_b = extras
    await _set_session_slider(pool, session_id, fid, slider=2)
    await _set_override(pool, target_id=target_id, session_id=session_id, fid=fid, slider=5)
    register_repo = RegisterRepository(pool)
    target_res = await register_repo.resolve_register(
        participant_id=target_id, session_id=session_id
    )
    sibling_a_res = await register_repo.resolve_register(
        participant_id=sibling_a, session_id=session_id
    )
    sibling_b_res = await register_repo.resolve_register(
        participant_id=sibling_b, session_id=session_id
    )
    assert target_res[2] == "participant_override"
    assert sibling_a_res == sibling_b_res
    assert sibling_a_res[2] == "session"
    assert sibling_a_res[0] == 2


# ---------------------------------------------------------------------------
# T046: override preset text differs from session preset text.
# ---------------------------------------------------------------------------


async def test_t046_override_preset_text_differs_from_session_preset(pool: asyncpg.Pool) -> None:
    """The override-targeted resolver returns the override's preset text."""
    session_id, fid, extras = await _make_session(pool, extra_participants=2)
    target_id, sibling_id = extras
    await _set_session_slider(pool, session_id, fid, slider=4)  # Technical
    await _set_override(pool, target_id=target_id, session_id=session_id, fid=fid, slider=1)
    register_repo = RegisterRepository(pool)
    _, target_p, target_src = await register_repo.resolve_register(
        participant_id=target_id, session_id=session_id
    )
    _, sibling_p, sibling_src = await register_repo.resolve_register(
        participant_id=sibling_id, session_id=session_id
    )
    assert (target_p.name, target_src) == ("direct", "participant_override")
    assert (sibling_p.name, sibling_src) == ("technical", "session")
    assert target_p.tier4_delta != sibling_p.tier4_delta


# ---------------------------------------------------------------------------
# T047: pause-resume idempotency.
# ---------------------------------------------------------------------------


async def test_t047_override_persists_across_pause_resume(pool: asyncpg.Pool) -> None:
    """Pausing and resuming the session leaves the override row intact."""
    from src.repositories.session_repo import SessionRepository

    session_id, fid, extras = await _make_session(pool, extra_participants=1)
    target_id = extras[0]
    register_repo = RegisterRepository(pool)
    session_repo = SessionRepository(pool)
    await _set_override(pool, target_id=target_id, session_id=session_id, fid=fid, slider=5)
    await session_repo.update_status(session_id, "paused")
    paused_row = await register_repo.get_participant_override(target_id)
    assert paused_row is not None and paused_row.slider_value == 5
    await session_repo.update_status(session_id, "active")
    resumed_row = await register_repo.get_participant_override(target_id)
    assert resumed_row is not None and resumed_row.slider_value == 5


# ---------------------------------------------------------------------------
# T048: participant remove cascades to override row.
# ---------------------------------------------------------------------------


async def test_t048_participant_delete_cascades_to_override_row(pool: asyncpg.Pool) -> None:
    """Removing a participant drops their override row (FR-015)."""
    session_id, fid, extras = await _make_session(pool, extra_participants=1)
    target_id = extras[0]
    register_repo = RegisterRepository(pool)
    await _set_override(pool, target_id=target_id, session_id=session_id, fid=fid, slider=5)
    assert await register_repo.get_participant_override(target_id) is not None
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM participants WHERE id = $1", target_id)
    assert await register_repo.get_participant_override(target_id) is None


# ---------------------------------------------------------------------------
# T049: session delete cascades; no _cleared audit row.
# ---------------------------------------------------------------------------


async def test_t049_session_delete_cascades_no_cleared_audit(pool: asyncpg.Pool) -> None:
    """Session delete drops overrides; cascade does NOT emit a _cleared audit."""
    from src.repositories.session_repo import SessionRepository

    session_id, fid, extras = await _make_session(pool, extra_participants=2)
    register_repo = RegisterRepository(pool)
    log_repo = LogRepository(pool)
    for target in extras:
        await _set_override(pool, target_id=target, session_id=session_id, fid=fid, slider=5)
    await SessionRepository(pool).delete_session(session_id)
    for target in extras:
        assert await register_repo.get_participant_override(target) is None
    cleared_audits = _filter_action(
        await log_repo.get_audit_log(session_id), "participant_register_override_cleared"
    )
    assert cleared_audits == []


async def _emit_override_cleared_audit(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    target_id: str,
    fid: str,
    cleared_slider: int,
    preset_name: str,
) -> None:
    """Emit the explicit-clear audit row."""
    await LogRepository(pool).log_register_change(
        action="participant_register_override_cleared",
        session_id=session_id,
        target_id=target_id,
        previous_value={"slider_value": cleared_slider, "preset": preset_name},
        new_value={"slider_value": None, "fallback_to": "session"},
        facilitator_id=fid,
    )


async def _count_overrides_for_session(pool: asyncpg.Pool, session_id: str) -> int:
    """Direct row count for orphan-check assertions."""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM participant_register_override WHERE session_id = $1",
            session_id,
        )


async def test_t049b_cascade_after_explicit_clear_keeps_clean_audit(pool: asyncpg.Pool) -> None:
    """Explicit clear followed by session delete: one _cleared row, no orphans."""
    from src.repositories.session_repo import SessionRepository

    session_id, fid, extras = await _make_session(pool, extra_participants=1)
    target_id = extras[0]
    register_repo = RegisterRepository(pool)
    await _set_override(pool, target_id=target_id, session_id=session_id, fid=fid, slider=5)
    cleared = await register_repo.clear_participant_override(target_id)
    assert cleared is not None
    await _emit_override_cleared_audit(
        pool,
        session_id=session_id,
        target_id=target_id,
        fid=fid,
        cleared_slider=5,
        preset_name="academic",
    )
    await SessionRepository(pool).delete_session(session_id)
    assert await _count_overrides_for_session(pool, session_id) == 0
    cleared_rows = _filter_action(
        await LogRepository(pool).get_audit_log(session_id),
        "participant_register_override_cleared",
    )
    assert len(cleared_rows) == 1
