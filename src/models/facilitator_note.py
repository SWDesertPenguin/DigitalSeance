# SPDX-License-Identifier: AGPL-3.0-or-later

"""FacilitatorNote frozen dataclass model.

Workspace-state row from the `facilitator_notes` table per spec 024.
Notes are operator-private; the FR-001 architectural test prevents
this model and the corresponding repository from being imported from
any AI context-assembly module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FacilitatorNote:
    """A facilitator-authored scratch note."""

    id: str
    session_id: str
    account_id: str | None
    actor_participant_id: str
    content: str
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    promoted_at: datetime | None
    promoted_message_turn: int | None
