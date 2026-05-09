# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 025 conclude-phase Tier 4 prompt delta.

Per spec 025 research.md §5 and data-model.md §ConcludeDelta, this module
holds the hardcoded conclude-delta text and the injection helper used by
the prompt assembler when the loop's current phase is `conclude`.

Composition order at Tier 4 (per research.md §4 forward-compatible
ordering): `custom_prompt` -> spec 021 register-slider delta (when 021
ships) -> conclude delta. All additive; the conclude delta MUST NOT
replace the participant's tier text or custom_prompt.
"""

from __future__ import annotations

CONCLUDE_DELTA_TEXT = (
    "The session is approaching its conclusion. In your next turn, "
    "please summarize your position so far and offer a final conclusion. "
    "The orchestrator will pause the loop after every active participant "
    "has had a turn to wrap up."
)


def conclude_delta(*, active: bool) -> str:
    """Return the conclude-phase Tier 4 delta when active; empty otherwise.

    A pure function so callers can pass `active=session.in_conclude_phase`
    and unconditionally hand the result to `assemble_prompt(...,
    conclude_delta=conclude_delta(active=...))`. When inactive, returns
    an empty string and the assembler is a no-op for the conclude
    fragment.
    """
    return CONCLUDE_DELTA_TEXT if active else ""
