"""Per-participant budget enforcement."""

from __future__ import annotations

from src.models.participant import Participant
from src.repositories.log_repo import LogRepository


class BudgetEnforcer:
    """Checks per-participant cost ceilings."""

    def __init__(self, log_repo: LogRepository) -> None:
        self._log_repo = log_repo

    async def check_budget(
        self,
        participant: Participant,
    ) -> bool:
        """Return True if participant is within budget."""
        if not _has_budget(participant):
            return True
        return await _within_limits(
            self._log_repo,
            participant,
        )


def _has_budget(participant: Participant) -> bool:
    """Check if any budget ceiling is configured."""
    return participant.budget_hourly is not None or participant.budget_daily is not None


async def _within_limits(
    log_repo: LogRepository,
    participant: Participant,
) -> bool:
    """Check both hourly and daily limits."""
    if participant.budget_hourly is not None:
        hourly = await log_repo.get_participant_cost(
            participant.id,
            period="hourly",
        )
        if hourly >= participant.budget_hourly:
            return False
    if participant.budget_daily is not None:
        daily = await log_repo.get_participant_cost(
            participant.id,
            period="daily",
        )
        if daily >= participant.budget_daily:
            return False
    return True
