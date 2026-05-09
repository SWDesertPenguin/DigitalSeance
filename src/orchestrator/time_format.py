# SPDX-License-Identifier: AGPL-3.0-or-later

"""UTC timestamp formatter for audit-log viewer (spec 029 FR-009).

Public surface (per ``specs/029-audit-log-viewer/contracts/shared-module-contracts.md`` §2):

- ``format_iso(dt)``: returns ``YYYY-MM-DDTHH:MM:SS.sssZ`` (millisecond precision,
  explicit ``Z`` UTC marker). Raises ``ValueError`` on naive (timezone-unaware)
  input.
- ``format_iso_or_none(dt | None)``: passes ``None`` through.

Output is fixed: millisecond precision (intentionally truncated from
microseconds for parity with JS ``Date`` precision), explicit ``Z`` marker,
no offset variants. The frontend mirror (``frontend/time_format.js``)'s
``formatIso`` produces byte-identical output for the same UTC instant; the
CI parity gate (``scripts/check_time_format_parity.py``) enforces.

Naive datetimes are rejected at the API boundary so callers must pass
timezone-aware values; this avoids ambiguous local-time interpretations
in audit data.
"""

from __future__ import annotations

from datetime import UTC, datetime


def format_iso(dt: datetime) -> str:
    """Format ``dt`` as UTC ISO-8601 with millisecond precision and ``Z`` marker.

    Example: ``2026-05-08T14:30:00.000Z``.

    Raises ``ValueError`` when ``dt`` has no timezone information; spec 029
    contract §2 requires timezone-aware input. Microseconds are truncated
    to milliseconds (parity with JS ``Date`` precision).
    """
    if dt.tzinfo is None:
        raise ValueError(
            "format_iso requires a timezone-aware datetime; got naive datetime " f"{dt!r}",
        )
    utc_dt = dt.astimezone(UTC)
    millis = utc_dt.microsecond // 1000
    return (
        f"{utc_dt.year:04d}-{utc_dt.month:02d}-{utc_dt.day:02d}"
        f"T{utc_dt.hour:02d}:{utc_dt.minute:02d}:{utc_dt.second:02d}"
        f".{millis:03d}Z"
    )


def format_iso_or_none(dt: datetime | None) -> str | None:
    """Wrapper for nullable timestamps; passes ``None`` through unchanged."""
    if dt is None:
        return None
    return format_iso(dt)
