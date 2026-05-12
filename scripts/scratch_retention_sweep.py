#!/usr/bin/env python3
"""Operator CLI: purge account-scoped facilitator notes past the retention window.

Spec 024 FR-018 + data-model.md retention sweep. Operators schedule this
externally (cron / Ofelia / k8s CronJob); v1 ships the script and NOT an
in-process scheduler per the spec assumptions.

Reads:
- ``SACP_DATABASE_URL`` (required)
- ``SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE`` (optional; empty/unset
  means indefinite retention — the sweep no-ops and exits 0)

Exits 0 on success (including the indefinite-retention no-op); non-zero on
configuration / connection failure. Prints the purged row count to stdout
for cron-mail capture.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg

from src.operations.retention_purge import purge_facilitator_notes_for_retention


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE for this run.",
    )
    return parser.parse_args()


def _retention_days(arg_override: int | None) -> int | None:
    """Resolve retention window. Returns None when retention is indefinite."""
    if arg_override is not None:
        return arg_override
    raw = os.environ.get("SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE", "")
    if raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        print(
            f"SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE must be integer or empty; got {raw!r}",
            file=sys.stderr,
        )
        sys.exit(2)


async def _run(retention_days: int) -> int:
    dsn = os.environ.get("SACP_DATABASE_URL")
    if not dsn:
        print("SACP_DATABASE_URL not set", file=sys.stderr)
        return 2
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    try:
        purged = await purge_facilitator_notes_for_retention(pool, retention_days)
    finally:
        await pool.close()
    print(f"purged {purged} facilitator_notes rows older than {retention_days} days")
    return 0


def main() -> int:
    args = _parse_args()
    retention_days = _retention_days(args.retention_days)
    if retention_days is None:
        print("SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE unset; no-op")
        return 0
    if retention_days <= 0:
        print(f"retention_days must be > 0; got {retention_days}", file=sys.stderr)
        return 2
    return asyncio.run(_run(retention_days))


if __name__ == "__main__":
    sys.exit(main())
