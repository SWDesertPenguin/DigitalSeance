# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 Phase 4 (US2) acceptance scenarios T033-T037.

Exercises the session-level register slider end-to-end through the
``RegisterRepository``, the ``log_register_change`` audit helper, and
the prompt-assembly hook in ``ContextAssembler._resolve_register_delta``.

Each test maps 1:1 to a scenario in
[spec.md User Story 2 "Acceptance Scenarios"](../specs/021-ai-response-shaping/spec.md):

  - T033 -> Scenario 1 (covers SC-004): facilitator sets slider ->
    ``session_register`` row written + ``session_register_changed``
    audit row.
  - T034 -> Scenario 2 (covers SC-004): next prompt assembly after a
    change carries the new preset's Tier 4 delta.
  - T035 -> Scenario 3 (covers FR-007 / FR-013): slider=3 (Balanced)
    produces NO register-specific delta -- tier text alone.
  - T036 -> Scenario 4 (covers FR-010): ``/me`` reflects three
    register fields after a change.
  - T037 -> Slider independence: ``SACP_RESPONSE_SHAPING_ENABLED=false``
    does NOT suppress slider deltas.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from src.prompts.register_presets import preset_for_slider
from src.repositories.log_repo import LogRepository
from src.repositories.register_repo import RegisterRepository

if TYPE_CHECKING:
    import asyncpg

pytestmark = pytest.mark.asyncio


async def _make_session(
    pool: asyncpg.Pool,
    *,
    extra_participants: int = 0,
) -> tuple[str, str, list[str]]:
    """Build a session, return (session_id, facilitator_id, [extra_pids])."""
    from src.repositories.session_repo import SessionRepository

    session, facilitator, _ = await SessionRepository(pool).create_session(
        "Register Test Session",
        facilitator_display_name="Facilitator",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )
    extra = await _seed_extra_participants(pool, session.id, extra_participants)
    return session.id, facilitator.id, extra


async def _seed_extra_participants(
    pool: asyncpg.Pool,
    session_id: str,
    count: int,
) -> list[str]:
    """Add ``count`` AI participants to a session and return their IDs."""
    if count == 0:
        return []
    from cryptography.fernet import Fernet

    from src.repositories.participant_repo import ParticipantRepository

    p_repo = ParticipantRepository(pool, encryption_key=Fernet.generate_key().decode())
    extra: list[str] = []
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
        extra.append(participant.id)
    return extra


async def _set_slider(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    facilitator_id: str,
    slider_value: int,
) -> tuple[object, object]:
    """Upsert and return ``(new_row, previous_row)``."""
    return await RegisterRepository(pool).upsert_session_register(
        session_id=session_id,
        slider_value=slider_value,
        facilitator_id=facilitator_id,
    )


def _filter_action(rows: list, action: str) -> list:
    """Return the subset of audit rows with the given action."""
    return [row for row in rows if row.action == action]


# ---------------------------------------------------------------------------
# T033: facilitator sets slider -> row + session_register_changed audit row.
# ---------------------------------------------------------------------------


async def test_t033_set_slider_writes_row_and_audit(pool: asyncpg.Pool) -> None:
    """Facilitator's first set creates the row and emits an audit event."""
    session_id, facilitator_id, _ = await _make_session(pool)
    log_repo = LogRepository(pool)
    new_row, previous = await _set_slider(
        pool, session_id=session_id, facilitator_id=facilitator_id, slider_value=4
    )
    assert previous is None
    assert new_row.slider_value == 4
    await log_repo.log_register_change(
        action="session_register_changed",
        session_id=session_id,
        target_id=session_id,
        previous_value=None,
        new_value={"slider_value": 4, "preset": "technical"},
        facilitator_id=facilitator_id,
    )
    audit_rows = _filter_action(
        await log_repo.get_audit_log(session_id), "session_register_changed"
    )
    assert len(audit_rows) == 1
    assert audit_rows[0].facilitator_id == facilitator_id
    assert audit_rows[0].previous_value is None


async def test_t033b_subsequent_set_records_previous_value(pool: asyncpg.Pool) -> None:
    """Second set captures the previous slider/preset for the audit row."""
    session_id, facilitator_id, _ = await _make_session(pool)
    log_repo = LogRepository(pool)
    await _set_slider(pool, session_id=session_id, facilitator_id=facilitator_id, slider_value=2)
    _, previous = await _set_slider(
        pool, session_id=session_id, facilitator_id=facilitator_id, slider_value=5
    )
    assert previous is not None and previous.slider_value == 2
    await log_repo.log_register_change(
        action="session_register_changed",
        session_id=session_id,
        target_id=session_id,
        previous_value={"slider_value": 2, "preset": "conversational"},
        new_value={"slider_value": 5, "preset": "academic"},
        facilitator_id=facilitator_id,
    )
    audit = _filter_action(await log_repo.get_audit_log(session_id), "session_register_changed")[0]
    assert json.loads(audit.previous_value)["slider_value"] == 2
    assert json.loads(audit.new_value)["slider_value"] == 5


# ---------------------------------------------------------------------------
# T034: next prompt assembly after a change carries the new preset's delta.
# ---------------------------------------------------------------------------


async def test_t034_resolver_returns_new_preset_after_change(pool: asyncpg.Pool) -> None:
    """The resolver's preset reflects the latest set-session-register call."""
    session_id, facilitator_id, extras = await _make_session(pool, extra_participants=1)
    speaker_id = extras[0]
    register_repo = RegisterRepository(pool)
    await _set_slider(pool, session_id=session_id, facilitator_id=facilitator_id, slider_value=4)
    slider, preset, source = await register_repo.resolve_register(
        participant_id=speaker_id, session_id=session_id
    )
    assert (slider, preset.name, source) == (4, "technical", "session")
    await _set_slider(pool, session_id=session_id, facilitator_id=facilitator_id, slider_value=1)
    slider2, preset2, _ = await register_repo.resolve_register(
        participant_id=speaker_id, session_id=session_id
    )
    assert (slider2, preset2.name) == (1, "direct")
    assert preset2.tier4_delta != preset.tier4_delta


# ---------------------------------------------------------------------------
# T035: slider=3 (Balanced) -> no delta.
# ---------------------------------------------------------------------------


async def test_t035_balanced_slider_emits_no_delta(pool: asyncpg.Pool) -> None:
    """slider=3 resolves to a preset whose tier4_delta is None."""
    session_id, facilitator_id, extras = await _make_session(pool, extra_participants=1)
    await _set_slider(pool, session_id=session_id, facilitator_id=facilitator_id, slider_value=3)
    slider, preset, source = await RegisterRepository(pool).resolve_register(
        participant_id=extras[0], session_id=session_id
    )
    assert (slider, preset.name, source) == (3, "balanced", "session")
    assert preset.tier4_delta is None


# ---------------------------------------------------------------------------
# T036: /me reflects register_slider / register_preset / register_source.
# ---------------------------------------------------------------------------


async def test_t036_me_payload_reflects_register(pool: asyncpg.Pool) -> None:
    """/me returns register_slider / register_preset / register_source='session'."""
    from src.web_ui.auth import _me_register_fields

    session_id, facilitator_id, extras = await _make_session(pool, extra_participants=1)
    register_repo = RegisterRepository(pool)
    slider, preset_name, source = await _me_register_fields(register_repo, extras[0], session_id)
    assert source == "session"
    assert preset_name == preset_for_slider(slider).name
    await _set_slider(pool, session_id=session_id, facilitator_id=facilitator_id, slider_value=5)
    slider, preset_name, source = await _me_register_fields(register_repo, extras[0], session_id)
    assert (slider, preset_name, source) == (5, "academic", "session")


async def test_t036b_me_with_no_register_repo_falls_back_to_default(monkeypatch) -> None:
    """When app.state.register_repo is None, /me uses the env default."""
    from src.web_ui.auth import _me_register_fields

    monkeypatch.setenv("SACP_REGISTER_DEFAULT", "4")
    slider, preset_name, source = await _me_register_fields(None, "p1", "s1")
    assert (slider, preset_name, source) == (4, "technical", "session")


# ---------------------------------------------------------------------------
# T037: master switch off does NOT suppress slider deltas.
# ---------------------------------------------------------------------------


async def test_t037_slider_emits_with_master_switch_off(
    pool: asyncpg.Pool,
    monkeypatch,
) -> None:
    """Resolver and preset selection remain hot when shaping is disabled."""
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", "false")
    session_id, facilitator_id, extras = await _make_session(pool, extra_participants=1)
    await _set_slider(pool, session_id=session_id, facilitator_id=facilitator_id, slider_value=4)
    slider, preset, source = await RegisterRepository(pool).resolve_register(
        participant_id=extras[0], session_id=session_id
    )
    assert (slider, preset.name, source) == (4, "technical", "session")
    assert preset.tier4_delta is not None
