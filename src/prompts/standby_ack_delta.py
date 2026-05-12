# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 027 always-mode standby acknowledgment Tier 4 prompt delta.

Per `specs/027-participant-standby-modes/spec.md` FR-015 / FR-016, this
module holds the hardcoded `always`-mode acknowledgment delta text and
the injection helper used by the prompt assembler when ANY detection
signal would have fired in `wait_for_human` mode for an `always`-mode
participant.

Composition order at Tier 4 (per Session 2026-05-12 Q5 fixed-additive
order): register-slider (spec 021) -> conclude (spec 025) -> standby
acknowledgment (spec 027). The wait-ack delta appends LAST so the
model sees the most-recent operational directive at the tail of the
assembled prompt.

The text is pre-validated through `src/security/output_validator.py`
at module import time (FR-022); any future amendment to the text
re-runs the validation in CI.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


STANDBY_ACK_TEXT = (
    "An unresolved condition awaits human input. In your next turn, "
    "briefly acknowledge the unmet wait, state the assumption you are "
    "making in the human's absence, then proceed with what you can "
    "advance now."
)


def _validate_text_at_import() -> None:
    """Run the hardcoded text through the security pipeline at import.

    FR-022 contract: the always-mode delta is system-tier content and
    therefore pre-validated. We deliberately keep this check tolerant of
    a missing/changed validator surface — the goal is to fail noisily on
    a definite pipeline-rejection, not to fail-import on every refactor
    of the security module.
    """
    try:
        from src.security.output_validator import validate as validate_output
    except ImportError:  # pragma: no cover - test substrate may stub this
        log.debug("standby_ack_delta: output_validator unavailable at import")
        return
    try:
        outcome = validate_output(STANDBY_ACK_TEXT)
    except Exception as exc:  # noqa: BLE001 - import-time best effort
        log.warning("standby_ack_delta_import_validate_failed: %s", exc)
        return
    if outcome is False:
        msg = "STANDBY_ACK_TEXT failed output_validator at module import"
        raise RuntimeError(msg)


_validate_text_at_import()


def standby_ack_delta(*, active: bool) -> str:
    """Return the always-mode Tier 4 delta when active; empty otherwise.

    A pure function so callers can pass
    ``active=is_always_mode_with_unresolved_gate(participant)`` and
    hand the result unconditionally to ``assemble_prompt(...,
    standby_ack_delta=standby_ack_delta(active=...))``. When inactive
    (no gate OR participant is in ``wait_for_human`` mode), returns an
    empty string and the assembler is a no-op for the standby-ack
    fragment.
    """
    return STANDBY_ACK_TEXT if active else ""
