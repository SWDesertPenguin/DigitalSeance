"""Role-based authorization guard functions.

Each guard raises a typed error on failure. Called at the
top of service methods — never returns a boolean.
"""

from __future__ import annotations

import asyncpg

from src.repositories.errors import NotFacilitatorError


async def require_facilitator(
    pool: asyncpg.Pool,
    session_id: str,
    caller_id: str,
) -> None:
    """Raise NotFacilitatorError if caller is not the facilitator."""
    async with pool.acquire() as conn:
        fid = await conn.fetchval(
            "SELECT facilitator_id FROM sessions WHERE id = $1",
            session_id,
        )
    if fid != caller_id:
        raise NotFacilitatorError("Caller is not the session facilitator")


async def require_role(
    pool: asyncpg.Pool,
    participant_id: str,
    *,
    expected: str,
) -> None:
    """Raise ValueError if participant does not have expected role."""
    async with pool.acquire() as conn:
        role = await conn.fetchval(
            "SELECT role FROM participants WHERE id = $1",
            participant_id,
        )
    if role != expected:
        msg = f"Expected role '{expected}', got '{role}'"
        raise ValueError(msg)


async def require_status(
    pool: asyncpg.Pool,
    participant_id: str,
    *,
    expected: str,
) -> None:
    """Raise ValueError if participant does not have expected status."""
    async with pool.acquire() as conn:
        status = await conn.fetchval(
            "SELECT status FROM participants WHERE id = $1",
            participant_id,
        )
    if status != expected:
        msg = f"Expected status '{expected}', got '{status}'"
        raise ValueError(msg)


def require_not_self(caller_id: str, target_id: str) -> None:
    """Raise ValueError if caller and target are the same."""
    if caller_id == target_id:
        msg = "Cannot perform this action on yourself"
        raise ValueError(msg)
