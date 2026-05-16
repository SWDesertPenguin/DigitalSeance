#!/usr/bin/env python3
"""Operator CLI: purge security_events rows past the retention window.

Per 007 §SC-009: operators schedule this externally (cron / Ofelia / k8s
CronJob). Default cadence is daily but enforcement is operator-side; this
script is a one-shot.

Reads:
- ``SACP_DATABASE_URL_CLEANUP`` (required) -- DSN connecting as the
  ``sacp_cleanup`` role, which has SELECT + DELETE on every table plus
  INSERT on ``admin_audit_log`` / ``security_events`` for the purge audit
  trail. See ``docs/env-vars.md`` for the variable definition and
  ``docs/runbooks/db-role-bootstrap.md`` for the bootstrap procedure.
- ``SACP_SECURITY_EVENTS_RETENTION_DAYS`` (optional; default 90 per 007 §SC-009)

Exits 0 on success; non-zero on connection / query failure. Prints the
deleted row count to stdout for cron-mail capture.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg

from src.operations.retention_purge import purge_security_events

DEFAULT_RETENTION_DAYS = 90


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override SACP_SECURITY_EVENTS_RETENTION_DAYS for this run.",
    )
    return parser.parse_args()


def _retention_days(arg_override: int | None) -> int:
    if arg_override is not None:
        return arg_override
    raw = os.environ.get("SACP_SECURITY_EVENTS_RETENTION_DAYS")
    if not raw:
        return DEFAULT_RETENTION_DAYS
    try:
        return int(raw)
    except ValueError:
        print(
            f"SACP_SECURITY_EVENTS_RETENTION_DAYS must be integer; got {raw!r}",
            file=sys.stderr,
        )
        sys.exit(2)


async def _run(retention_days: int) -> int:
    dsn = os.environ.get("SACP_DATABASE_URL_CLEANUP")
    if not dsn:
        print(
            "SACP_DATABASE_URL_CLEANUP not set (see docs/env-vars.md)",
            file=sys.stderr,
        )
        return 2
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    try:
        deleted = await purge_security_events(pool, retention_days)
    finally:
        await pool.close()
    print(f"purged {deleted} security_events rows older than {retention_days} days")
    return 0


def main() -> int:
    args = _parse_args()
    retention_days = _retention_days(args.retention_days)
    if retention_days <= 0:
        print(f"retention_days must be > 0; got {retention_days}", file=sys.stderr)
        return 2
    return asyncio.run(_run(retention_days))


if __name__ == "__main__":
    sys.exit(main())
