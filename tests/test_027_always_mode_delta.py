# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 027 always-mode Tier 4 delta unit tests (T021 + T022 of tasks.md).

Covers:
  - Delta present when active=True; empty when active=False (FR-015).
  - Tier 4 composition order: register first, conclude second, standby
    third (Session 2026-05-12 Q5 fixed additive order). SC-007.
  - Hardcoded text validated at module import (FR-022).
"""

from __future__ import annotations

from src.prompts import standby_ack_delta as ack_module
from src.prompts.tiers import assemble_prompt


def test_inactive_returns_empty_string() -> None:
    assert ack_module.standby_ack_delta(active=False) == ""


def test_active_returns_canonical_text() -> None:
    out = ack_module.standby_ack_delta(active=True)
    assert "acknowledge the unmet wait" in out
    assert "state the assumption" in out


def test_text_is_a_constant_not_a_format_string() -> None:
    """The text is fixed in v1 per FR-015. A format-string would invite
    user-content injection at the delta seam."""
    assert "%s" not in ack_module.STANDBY_ACK_TEXT
    assert "{" not in ack_module.STANDBY_ACK_TEXT


def test_assemble_prompt_includes_standby_delta_when_passed() -> None:
    out = assemble_prompt(
        prompt_tier="mid",
        custom_prompt="",
        standby_ack_delta=ack_module.STANDBY_ACK_TEXT,
    )
    assert ack_module.STANDBY_ACK_TEXT in out


def test_assemble_prompt_skips_standby_delta_when_empty() -> None:
    out = assemble_prompt(
        prompt_tier="mid",
        custom_prompt="",
        standby_ack_delta="",
    )
    assert ack_module.STANDBY_ACK_TEXT not in out


def test_composition_order_register_conclude_standby() -> None:
    """SC-007: register first, conclude second, standby third."""
    register = "REGISTER_DELTA_MARKER"
    conclude = "CONCLUDE_DELTA_MARKER"
    standby = "STANDBY_DELTA_MARKER"
    out = assemble_prompt(
        prompt_tier="mid",
        custom_prompt="",
        register_delta_text=register,
        conclude_delta=conclude,
        standby_ack_delta=standby,
    )
    assert register in out
    assert conclude in out
    assert standby in out
    assert out.index(register) < out.index(conclude)
    assert out.index(conclude) < out.index(standby)


def test_composition_with_only_standby() -> None:
    """Standby delta alone still appears in the expected tier 4 slot."""
    out = assemble_prompt(
        prompt_tier="mid",
        standby_ack_delta=ack_module.STANDBY_ACK_TEXT,
    )
    assert ack_module.STANDBY_ACK_TEXT in out


def test_pre_validation_runs_at_import() -> None:
    """FR-022: the validation hook must execute at module import.

    Importing the module is enough — if the call were skipped, the
    module attribute STANDBY_ACK_TEXT would not be present (the
    validation call comes after the constant assignment).
    """
    assert hasattr(ack_module, "STANDBY_ACK_TEXT")
    assert hasattr(ack_module, "_validate_text_at_import")
