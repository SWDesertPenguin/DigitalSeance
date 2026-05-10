# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 SC-005 timing-attack-resistance test (T040).

The login endpoint MUST run :meth:`PasswordHasher.verify` against a
pinned dummy hash on the email-miss path so an attacker cannot
distinguish "email not registered" from "email registered, wrong
password" via response timing.

The test takes mean elapsed time over a small sample (default 8 calls)
for each branch and asserts the means are within ±5 ms. We sample
multiple times rather than measuring a single call to absorb the
inherent jitter of the test harness; argon2id is the dominant cost
on both branches so the means converge tightly when the
implementation is correct.

If this test ever fails, the regression is almost always:

1. The email-miss branch returns early without calling verify().
2. The email-miss branch uses a different (cheaper) hasher.
3. The dummy hash uses different argon2id parameters than the real
   account's stored hash (re-hash drift).

All three break SC-005. The test is the single safety net.
"""

from __future__ import annotations

import time
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from src.accounts.rate_limit import LoginRateLimiter
from src.accounts.service import AccountService
from src.repositories.account_repo import AccountRepository
from src.repositories.log_repo import LogRepository
from src.web_ui.app import create_web_app
from src.web_ui.security import CSRF_HEADER, CSRF_VALUE
from src.web_ui.session_store import SessionStore

_CSRF = {CSRF_HEADER: CSRF_VALUE}

# Sample size per branch. Larger N reduces jitter at the cost of test
# runtime; argon2 verify at our test floor (time_cost=1, mem=8 MiB)
# clocks ~5-15 ms per call, so 8 samples per branch keeps the test
# under ~250 ms while giving the mean enough samples to be stable.
_SAMPLE_N = 8


@pytest.fixture(autouse=True)
def _accounts_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("SACP_PASSWORD_ARGON2_MEMORY_COST_KB", "8192")


@pytest.fixture
async def app_with_seeded_account(pool: asyncpg.Pool) -> Any:
    """Build the app + verify one account so the email-hit branch is real."""
    app = create_web_app()
    app.state.pool = pool
    log_repo = LogRepository(pool)
    session_store = SessionStore()
    app.state.log_repo = log_repo
    app.state.session_store = session_store
    service = AccountService(
        account_repo=AccountRepository(pool),
        log_repo=log_repo,
        session_store=session_store,
        # High threshold so the rate limiter never fires during sampling.
        rate_limiter=LoginRateLimiter(threshold=10_000),
    )
    app.state.account_service = service
    create = await service.create_account(
        email="timing@example.com",
        password="correct-password-1",  # noqa: S106 -- test fixture
        client_ip="127.0.0.1",
    )
    plaintext = create.dev_plaintext_code
    assert plaintext is not None
    await service.verify_account(account_id=create.account_id, code=plaintext)
    return app


def _measure_login(client: TestClient, *, email: str, password: str) -> float:
    """Issue one login call; return elapsed wall-clock seconds."""
    start = time.perf_counter()
    response = client.post(
        "/tools/account/login",
        json={"email": email, "password": password},
        headers=_CSRF,
    )
    elapsed = time.perf_counter() - start
    assert response.status_code == 401
    return elapsed


def _mean_ms(samples: list[float]) -> float:
    """Mean across ``samples`` in milliseconds (drops the one slowest)."""
    # Drop the one slowest sample on each side to absorb GC pauses /
    # I/O hiccups; the contract is about the typical response, not
    # the worst-case outlier.
    trimmed = sorted(samples)[: -1 or None]
    return 1000.0 * sum(trimmed) / len(trimmed)


def _warm_up_both_branches(client: TestClient) -> None:
    """One call on each login branch so warmup doesn't bias the first measured."""
    _measure_login(
        client,
        email="warmup-miss@example.com",
        password="any-password-12",  # noqa: S106 -- test fixture
    )
    _measure_login(
        client,
        email="timing@example.com",
        password="wrong-password-99",  # noqa: S106 -- test fixture
    )


def _sample_miss_branch(client: TestClient) -> list[float]:
    """Sample N email-miss-branch login calls."""
    return [
        _measure_login(
            client,
            email=f"miss{i}@example.com",
            password="any-password-12",  # noqa: S106 -- test fixture
        )
        for i in range(_SAMPLE_N)
    ]


def _sample_wrong_password_branch(client: TestClient) -> list[float]:
    """Sample N wrong-password-branch login calls against the seeded account."""
    return [
        _measure_login(
            client,
            email="timing@example.com",
            password="wrong-password-99",  # noqa: S106 -- test fixture
        )
        for _ in range(_SAMPLE_N)
    ]


async def test_login_timing_uniform_across_failure_modes(
    app_with_seeded_account: Any,
) -> None:
    """SC-005: ±5ms between non-existent-email vs. wrong-password paths."""
    with TestClient(app_with_seeded_account) as client:
        _warm_up_both_branches(client)
        miss_samples = _sample_miss_branch(client)
        wrong_samples = _sample_wrong_password_branch(client)
    miss_mean_ms = _mean_ms(miss_samples)
    wrong_mean_ms = _mean_ms(wrong_samples)
    delta = abs(miss_mean_ms - wrong_mean_ms)
    # The ±5 ms contract is per spec SC-005. Argon2 dominates the
    # request cost on both branches when the dummy-hash pattern is
    # correctly applied; jitter from Python interpretation + DB I/O
    # adds <1 ms on average. A delta > 5 ms is the canary that the
    # email-miss branch is short-circuiting verify().
    assert delta < 5.0, (
        f"SC-005 timing leak: miss-mean={miss_mean_ms:.2f}ms vs. "
        f"wrong-mean={wrong_mean_ms:.2f}ms (delta={delta:.2f}ms > 5.0ms). "
        "The email-miss branch is likely short-circuiting argon2id verify()."
    )


async def test_login_timing_email_miss_runs_argon2(
    app_with_seeded_account: Any,
) -> None:
    """A non-existent-email login MUST take meaningful time (argon2id).

    If the email-miss branch were a fast no-op, the response would
    return in microseconds. We assert the call takes at least a
    millisecond so a regression that drops the dummy-verify call is
    caught even before the ±5ms equality test.
    """
    with TestClient(app_with_seeded_account) as client:
        # Warm-up.
        _measure_login(
            client,
            email="warmup@example.com",
            password="any-password-12",  # noqa: S106 -- test fixture
        )
        elapsed = _measure_login(
            client,
            email="ghost@example.com",
            password="any-password-12",  # noqa: S106 -- test fixture
        )
    elapsed_ms = elapsed * 1000.0
    assert elapsed_ms > 1.0, (
        f"SC-005 short-circuit: email-miss login returned in {elapsed_ms:.3f}ms "
        "— argon2id verify is not running on the miss path."
    )
