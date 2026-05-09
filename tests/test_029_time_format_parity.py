# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 029 time-formatter tests (T013 of tasks.md).

Covers ``src/orchestrator/time_format.py``:

- ``format_iso`` output for fixed UTC instants (millisecond precision,
  ``Z`` marker, microsecond truncation).
- ``ValueError`` on naive (timezone-unaware) datetime input.
- ``format_iso_or_none`` ``None`` passthrough.
- Parity-script happy path: backend + shipped JS mirror agree across
  every fixture in ``scripts/check_time_format_parity.py``. The script
  invokes Node; when Node is unavailable the parity test is marked as
  expected-to-fail with a rationale.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.orchestrator.time_format import format_iso, format_iso_or_none

REPO_ROOT = Path(__file__).resolve().parent.parent
PARITY_SCRIPT = REPO_ROOT / "scripts" / "check_time_format_parity.py"


# ---------------------------------------------------------------------------
# format_iso shape
# ---------------------------------------------------------------------------


def test_format_iso_epoch_zero() -> None:
    out = format_iso(datetime(1970, 1, 1, tzinfo=UTC))
    assert out == "1970-01-01T00:00:00.000Z"


def test_format_iso_truncates_microseconds_to_milliseconds() -> None:
    dt = datetime(2026, 5, 8, 14, 30, 0, 123456, tzinfo=UTC)
    assert format_iso(dt) == "2026-05-08T14:30:00.123Z"


def test_format_iso_high_millisecond_padding() -> None:
    dt = datetime(2026, 5, 8, 14, 30, 0, 999000, tzinfo=UTC)
    assert format_iso(dt) == "2026-05-08T14:30:00.999Z"


def test_format_iso_pads_low_millisecond() -> None:
    dt = datetime(2026, 5, 8, 14, 30, 0, 7000, tzinfo=UTC)
    assert format_iso(dt) == "2026-05-08T14:30:00.007Z"


def test_format_iso_renders_nonutc_as_utc() -> None:
    """Non-UTC tzinfo input must be converted to UTC before formatting."""
    east5 = timezone(timedelta(hours=-5))
    dt = datetime(2026, 5, 8, 9, 30, 0, tzinfo=east5)
    assert format_iso(dt) == "2026-05-08T14:30:00.000Z"


def test_format_iso_rejects_naive_datetime() -> None:
    naive = datetime(2026, 5, 8, 14, 30, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        format_iso(naive)


# ---------------------------------------------------------------------------
# format_iso_or_none
# ---------------------------------------------------------------------------


def test_format_iso_or_none_passes_none_through() -> None:
    assert format_iso_or_none(None) is None


def test_format_iso_or_none_formats_aware_datetime() -> None:
    dt = datetime(2026, 5, 8, 14, 30, 0, tzinfo=UTC)
    assert format_iso_or_none(dt) == "2026-05-08T14:30:00.000Z"


# ---------------------------------------------------------------------------
# Parity gate
# ---------------------------------------------------------------------------


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="node not on PATH")
def test_parity_script_passes_against_shipped_mirror() -> None:
    """Happy path: backend format_iso + JS formatIso agree for every fixture."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(PARITY_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, (
        f"time-format parity gate failed unexpectedly:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
