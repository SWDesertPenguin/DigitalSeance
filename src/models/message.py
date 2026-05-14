# SPDX-License-Identifier: AGPL-3.0-or-later

"""Message frozen dataclass model — immutable transcript entry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Message:
    """An immutable conversation transcript entry.

    Composite identity: (turn_number, session_id, branch_id).
    """

    turn_number: int
    session_id: str
    branch_id: str
    parent_turn: int | None
    speaker_id: str
    speaker_type: str
    delegated_from: str | None
    complexity_score: str
    content: str
    token_count: int
    cost_usd: float | None
    created_at: datetime
    summary_epoch: int | None
    # Spec 028 — CAPCOM-like routing scope.
    kind: str = "utterance"
    visibility: str = "public"

    @classmethod
    def from_record(cls, record: Any) -> Message:
        """Construct a Message from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})
