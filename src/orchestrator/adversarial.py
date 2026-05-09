# SPDX-License-Identifier: AGPL-3.0-or-later

"""Adversarial rotation — periodic challenger prompt injection."""

from __future__ import annotations

DEFAULT_INTERVAL = 12
ADVERSARIAL_PROMPT = (
    "Identify the weakest assumption in the current direction "
    "and argue against it. If you genuinely cannot find a flaw, "
    "say so explicitly and explain why."
)


class AdversarialRotator:
    """Manages adversarial prompt injection rotation."""

    def __init__(
        self,
        *,
        interval: int = DEFAULT_INTERVAL,
    ) -> None:
        self._interval = interval
        self._counters: dict[str, int] = {}
        self._rotation: dict[str, int] = {}

    def should_inject(self, session_id: str) -> bool:
        """Check if adversarial prompt should fire."""
        count = self._counters.get(session_id, 0)
        return count >= self._interval

    def get_prompt(self) -> str:
        """Return the adversarial prompt text."""
        return ADVERSARIAL_PROMPT

    def get_target_index(
        self,
        session_id: str,
        num_participants: int,
    ) -> int:
        """Get the participant index for this rotation."""
        idx = self._rotation.get(session_id, 0)
        return idx % num_participants if num_participants > 0 else 0

    def advance(self, session_id: str) -> None:
        """Increment turn counter."""
        self._counters[session_id] = self._counters.get(session_id, 0) + 1

    def reset_and_rotate(self, session_id: str) -> None:
        """Reset counter and advance rotation index."""
        self._counters[session_id] = 0
        self._rotation[session_id] = self._rotation.get(session_id, 0) + 1
