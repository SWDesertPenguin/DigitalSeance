#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Time-formatter parity CI gate (spec 029 FR-009 / research.md §5).

Asserts byte-equal output of ``src/orchestrator/time_format.format_iso``
and ``frontend/time_format.formatIso`` for a fixed set of UTC instants.

Fixtures cover:

- Epoch (``1970-01-01T00:00:00Z``)
- A US-DST transition instant (``2026-03-08T07:00:00Z``)
- A microsecond-precise UTC instant (truncated to milliseconds for both)
- A non-UTC timezone-aware datetime (forces both sides to render as UTC)
- A high-millisecond instant (``...999Z``) to catch off-by-one rollover

The Python module is imported directly. The JS module is invoked via
``node -e``; the script piggybacks on the Node already required for the
frontend test suite.

``formatLocale`` and ``formatRelative`` are NOT parity-checked - their
output legitimately varies across browsers (locale, RTL handling).

Usage:
    python scripts/check_time_format_parity.py

Exit codes:
    0 = parity for every fixture
    1 = drift (with diff written to stderr)
    2 = environment problem (Node missing or JS module load failed)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JS_MODULE = REPO_ROOT / "frontend" / "time_format.js"

sys.path.insert(0, str(REPO_ROOT))

from src.orchestrator.time_format import format_iso  # noqa: E402,I001


def _build_fixtures() -> list[tuple[str, datetime]]:
    """Return ``(name, dt)`` fixture pairs covering the parity contract."""
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    dst = datetime(2026, 3, 8, 7, 0, 0, tzinfo=UTC)
    micros = datetime(2026, 5, 8, 14, 30, 0, 123456, tzinfo=UTC)
    high_ms = datetime(2026, 5, 8, 14, 30, 0, 999000, tzinfo=UTC)
    east5 = timezone(timedelta(hours=-5))
    nonutc = datetime(2026, 5, 8, 9, 30, 0, tzinfo=east5)
    return [
        ("epoch", epoch),
        ("dst-transition", dst),
        ("microsecond-truncation", micros),
        ("high-millisecond", high_ms),
        ("nonutc-timezone", nonutc),
    ]


def _format_iso_via_node(dt: datetime) -> str:
    """Invoke ``frontend/time_format.formatIso`` and return its output."""
    iso_input = dt.isoformat()
    js_path_literal = str(JS_MODULE).replace("\\", "\\\\")
    script = (
        f"const m = require('{js_path_literal}');"
        f"process.stdout.write(m.formatIso('{iso_input}'));"
    )
    result = subprocess.run(  # noqa: S603
        [_node_executable(), "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"node invocation failed: {result.stderr.strip() or result.stdout.strip()}",
        )
    return result.stdout


def _node_executable() -> str:
    exe = shutil.which("node")
    if exe is None:
        raise RuntimeError("node executable not found on PATH")
    return exe


def main() -> int:
    try:
        _node_executable()
    except RuntimeError as e:
        sys.stderr.write(f"time-format parity gate skipped: {e}\n")
        return 2
    drifted: list[tuple[str, str, str]] = []
    for name, dt in _build_fixtures():
        py_out = format_iso(dt)
        js_out = _format_iso_via_node(dt)
        if py_out != js_out:
            drifted.append((name, py_out, js_out))
    if drifted:
        sys.stderr.write(
            "time-format parity drift detected "
            "(spec 029 FR-009; shared-module-contracts.md §5):\n",
        )
        for name, py_out, js_out in drifted:
            sys.stderr.write(f"  {name}: python={py_out!r} js={js_out!r}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
