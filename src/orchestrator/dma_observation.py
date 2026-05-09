# SPDX-License-Identifier: AGPL-3.0-or-later

"""Process-scope in-memory ring buffer for spec 014 density-anomaly sampling.

Spec 014's density-anomaly signal source samples the count of recent
anomalies on the controller's synchronous decision-cycle hot path; the
convergence detector records anomalies on an async DB write path. This
module bridges the two without putting a DB call on the hot path.

The buffer is process-scope and bounded; entries older than the longest
practical sampling window are dropped on append.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta

# Bounded so a long-running orchestrator can't grow this unbounded under
# pathological anomaly rates. ~10k entries covers >2 hours at 1/s sustained.
_BUFFER: deque[tuple[datetime, str]] = deque(maxlen=10_000)


def record_density_anomaly(session_id: str, when: datetime | None = None) -> None:
    """Append a density-anomaly observation to the in-memory buffer.

    Called from the convergence detector immediately after a
    ``tier='density_anomaly'`` row is persisted to ``convergence_log``.
    """
    _BUFFER.append((when or datetime.now(UTC), session_id))


def count_recent_density_anomalies(
    session_id: str,
    *,
    window_seconds: int = 60,
    now: datetime | None = None,
) -> int:
    """Return the count of anomalies for ``session_id`` in the last ``window_seconds``."""
    cutoff = (now or datetime.now(UTC)) - timedelta(seconds=window_seconds)
    return sum(1 for ts, sid in _BUFFER if sid == session_id and ts >= cutoff)


def reset_for_tests() -> None:
    """Clear the buffer; for use in test fixtures only."""
    _BUFFER.clear()
