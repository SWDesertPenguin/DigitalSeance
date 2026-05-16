# SPDX-License-Identifier: AGPL-3.0-or-later

"""Audit C-02 v2: timing-attack smoke test for `_find_by_token`.

Pre-fix v1 the failure path returned in sub-millisecond time when the
HMAC probe missed (no row), while the success path paid bcrypt's
~100ms verify cost. An attacker captures wall-clock latency for many
candidate tokens and partitions them into "HMAC hit" vs "HMAC miss"
buckets -- once an attacker captures the HMAC lookup key they can
enumerate valid lookups offline without ever needing the bcrypt hash.

Post-fix the no-row path runs a dummy bcrypt so the wall-clock cost
matches the success path. This test confirms the medians are within
+/-10%.

Tolerance choice: bcrypt's cost is the dominant term; on a quiet
CI runner the noise floor is well under 10%. If this test starts
flaking, investigate before widening the tolerance -- a regression
that re-introduces the timing channel is the failure mode this guard
exists to catch.
"""

from __future__ import annotations

import contextlib
import statistics
import time

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.auth.service import AuthService
from src.repositories.errors import TokenInvalidError
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()
WARMUP_ITERATIONS = 3
MEASURE_ITERATIONS = 12
TOLERANCE = 0.10


@pytest.fixture
async def session_pid(pool: asyncpg.Pool) -> tuple[str, str]:
    """Create a session and return (session_id, facilitator_id)."""
    session_repo = SessionRepository(pool)
    session, _, _ = await session_repo.create_session(
        "Timing Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, session.facilitator_id


@pytest.fixture
def auth(pool: asyncpg.Pool) -> AuthService:
    """Provide an AuthService."""
    return AuthService(pool, encryption_key=TEST_KEY)


async def _add_with_token(pool: asyncpg.Pool, session_id: str, token: str) -> str:
    """Helper: add a participant carrying `token`; return their id."""
    repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant, _ = await repo.add_participant(
        session_id=session_id,
        display_name="Bob",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auth_token=token,
        auto_approve=True,
    )
    return participant.id


async def _time_success(auth: AuthService, token: str) -> float:
    """Return wall-clock seconds for one successful authenticate()."""
    start = time.perf_counter()
    await auth.authenticate(token, "127.0.0.1")
    return time.perf_counter() - start


async def _time_failure(auth: AuthService, token: str) -> float:
    """Return wall-clock seconds for one TokenInvalidError-raising call."""
    start = time.perf_counter()
    with contextlib.suppress(TokenInvalidError):
        await auth.authenticate(token, "127.0.0.1")
    return time.perf_counter() - start


async def _collect_samples(
    runner,
    auth: AuthService,
    token: str,
) -> list[float]:
    """Run warm-up + measure iterations and return only the measurements."""
    for _ in range(WARMUP_ITERATIONS):
        await runner(auth, token)
    return [await runner(auth, token) for _ in range(MEASURE_ITERATIONS)]


async def test_failure_timing_matches_success(
    auth: AuthService,
    pool: asyncpg.Pool,
    session_pid: tuple[str, str],
) -> None:
    """No-row failure path's wall-clock median is within +/-10% of success."""
    sid, _ = session_pid
    await _add_with_token(pool, sid, "valid-timing-token")  # noqa: S106
    success_samples = await _collect_samples(_time_success, auth, "valid-timing-token")
    failure_samples = await _collect_samples(_time_failure, auth, "no-such-token")
    success_median = statistics.median(success_samples)
    failure_median = statistics.median(failure_samples)
    ratio = failure_median / success_median
    assert 1.0 - TOLERANCE <= ratio <= 1.0 + TOLERANCE, (
        f"timing channel detected: failure_median={failure_median:.4f}s "
        f"success_median={success_median:.4f}s ratio={ratio:.3f} "
        f"(tolerance +/-{TOLERANCE:.0%})"
    )
