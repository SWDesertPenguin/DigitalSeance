# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-dispatch compression_log writer — spec 026 FR-005, FR-007, SC-013.

The CompressorService writes one row per `compress(...)` invocation
(including NoOp). This repository hosts the INSERT helper. The FastAPI
lifespan wires `set_writer(...)` against
`src.compression._telemetry_sink` so production writes flow through
asyncpg; tests inspect the in-memory accumulator default.

Append-only per spec 001 §FR-008. Schema mirrored in
``tests/conftest.py`` per ``feedback_test_schema_mirror``.
"""

from __future__ import annotations

import asyncpg

from src.compression._telemetry_sink import CompressionLogRecord


async def insert_compression_log(
    pool: asyncpg.Pool,
    record: CompressionLogRecord,
) -> None:
    """Insert one row into `compression_log`.

    Caller MUST have already populated every field of `record`.
    `succeeded=False` rows record the source-token count + zero
    output-tokens per spec 026 FR-020 fail-soft path. The marker
    routing-log emission lives at the call site, not here.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO compression_log (
                session_id, turn_id, participant_id,
                source_tokens, output_tokens,
                compressor_id, compressor_version,
                trust_tier, layer, duration_ms
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            record.session_id,
            record.turn_id,
            record.participant_id,
            record.source_tokens,
            record.output_tokens,
            record.compressor_id,
            record.compressor_version,
            record.trust_tier,
            record.layer,
            record.duration_ms,
        )
