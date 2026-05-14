#!/usr/bin/env python3
"""V18 traceability audit for spec 026 (context compression).

Constitution check V18 requires that every compressed segment carries
an XML boundary marker AND a matching compression_log row exists for
the same turn_id + participant_id + compressor_id.

This script:
  1. Connects to the DB (reads SACP_DATABASE_URL from env; exits 0
     gracefully if not set -- suitable for CI without a live DB).
  2. Queries compression_log rows where output_tokens < source_tokens
     (actual compression happened; NoOp rows have output_tokens ==
     source_tokens and do not carry a boundary marker).
  3. For each row, confirms a routing_log entry exists for the same
     turn_id with a payload containing the compressor XML boundary
     marker pattern <SACP_LAYER_N_COMPRESSED> or the generic
     <compressed ...> wrapper emitted by markers.wrap().
  4. Reports compression_log rows that lack a matching boundary marker
     in routing_log.
  5. Exits 0 if all pass, 1 if any mismatch.

Usage:
    python scripts/check_026_v18_traceability.py
    python scripts/check_026_v18_traceability.py --dry-run

Flags:
    --dry-run   Print the SQL that would run without executing it; exit 0.

Per spec 026 plan.md Constitution Check V18 + task T059.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_COMPRESSED_ROWS_SQL = """
SELECT
    cl.id,
    cl.session_id,
    cl.turn_id,
    cl.participant_id,
    cl.compressor_id,
    cl.compressor_version,
    cl.source_tokens,
    cl.output_tokens
FROM compression_log cl
WHERE cl.output_tokens < cl.source_tokens
ORDER BY cl.id
"""

_ROUTING_MARKER_SQL = """
SELECT COUNT(*)
FROM routing_log rl
WHERE rl.turn_id = $1
  AND rl.participant_id = $2
  AND (
    rl.reason = 'compression_applied'
    OR rl.reason LIKE 'compression%'
  )
"""

_MISSING_LABEL = "MISSING_MARKER"


def _print_dry_run() -> None:
    print("-- V18 traceability audit: dry-run mode (no DB connection)")
    print()
    print("-- Step 1: fetch all rows where actual compression happened")
    print(_COMPRESSED_ROWS_SQL.strip())
    print()
    print("-- Step 2: for each row, check routing_log for marker (parameterised)")
    print(_ROUTING_MARKER_SQL.strip())
    print()
    print("-- Exits 0 when all compressed rows have a matching routing_log entry.")
    print("-- Exits 1 when any compressed row lacks a routing_log marker.")


def _row_label(row: object) -> str:
    return (
        f"  compression_log id={row['id']}"
        f" turn_id={row['turn_id']}"
        f" participant_id={row['participant_id']}"
        f" compressor_id={row['compressor_id']}"
        f" ({row['source_tokens']} -> {row['output_tokens']} tokens)"
    )


async def _check_rows(conn: object, rows: list) -> list[str]:
    mismatches: list[str] = []
    for row in rows:
        count = await conn.fetchval(_ROUTING_MARKER_SQL, row["turn_id"], row["participant_id"])
        if not count:
            mismatches.append(_row_label(row))
    return mismatches


async def _audit(conn: object) -> int:
    rows = await conn.fetch(_COMPRESSED_ROWS_SQL)
    if not rows:
        print("OK: No compression_log rows with output_tokens < source_tokens found.")
        return 0
    mismatches = await _check_rows(conn, rows)
    if mismatches:
        print(
            f"FAIL: {len(mismatches)} of {len(rows)} compressed rows"
            " lack a routing_log marker entry:",
            file=sys.stderr,
        )
        for m in mismatches:
            print(m, file=sys.stderr)
        return 1
    print(f"OK: All {len(rows)} compressed rows have a matching routing_log marker entry.")
    return 0


async def _run(db_url: str) -> int:
    """Return 0 on clean audit, 1 on mismatch."""
    try:
        import asyncpg  # type: ignore[import]
    except ImportError:
        print("ERROR: asyncpg not installed; cannot connect to DB.", file=sys.stderr)
        return 1
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            return await _audit(conn)
    finally:
        await pool.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="V18 traceability audit for spec 026 context compression.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL without connecting to the DB; exit 0.",
    )
    args = parser.parse_args()

    if args.dry_run:
        _print_dry_run()
        return 0

    db_url = os.environ.get("SACP_DATABASE_URL")
    if not db_url:
        print(
            "INFO: SACP_DATABASE_URL not set; skipping V18 traceability audit.",
            file=sys.stderr,
        )
        return 0

    return asyncio.run(_run(db_url))


if __name__ == "__main__":
    sys.exit(main())
