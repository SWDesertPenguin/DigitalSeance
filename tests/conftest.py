# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared pytest fixtures for SACP database tests."""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import httpx
import pytest
from cryptography.fernet import Fernet

# Ensure test database URL is set. Default password matches CI
# (.github/workflows/test.yml) so local + CI use the same credentials, AND
# is non-placeholder so the V16 validator (audit H-04) doesn't refuse-to-bind
# during meta-tests of the validator itself.
TEST_DB_URL = os.environ.get(
    "SACP_TEST_DATABASE_URL",
    "postgresql://sacp_test:testpass@localhost:5432/sacp_test",
)

# Audit C-02: every repo write that hashes a token also computes an HMAC
# token-lookup keyed by SACP_AUTH_LOOKUP_KEY. Set a deterministic value at
# import time so every test (DB-backed or not) can exercise auth paths
# without each suite re-setting the env var. Tests that exercise the V16
# validator for this var override it themselves.
os.environ.setdefault(
    "SACP_AUTH_LOOKUP_KEY",
    "test-only-auth-lookup-key-do-not-use-in-prod-32chars-min",
)

# Audit M-02: Web UI cookie signing now uses SACP_WEB_UI_COOKIE_KEY,
# distinct from SACP_ENCRYPTION_KEY. Set a deterministic test value so
# auth / WS suites can mint and parse cookies without each test re-
# setting the env var. Tests that exercise the V16 validator override.
os.environ.setdefault(
    "SACP_WEB_UI_COOKIE_KEY",
    "test-only-cookie-key-do-not-use-in-prod-32chars-minimum",
)


@pytest.fixture(scope="session", autouse=True)
def _spec_020_register_adapters() -> None:
    """Spec 020: ensure both adapters are registered for the test session.

    Production-path init runs in `src/mcp_server/app.py:_lifespan`. Tests
    that exercise dispatch outside of the FastAPI lifespan (e.g.,
    `test_loop_integration.py`'s direct `loop.execute_turn(...)` calls
    via `mock_litellm`) need the LiteLLM adapter registered so
    `get_adapter()` returns an instance. This session-scoped fixture
    imports both adapter packages so the registry is populated; the
    individual adapter selection is still env-var-driven via
    `SACP_PROVIDER_ADAPTER` per FR-002.
    """
    import src.api_bridge.litellm  # noqa: F401
    import src.api_bridge.mock  # noqa: F401


@pytest.fixture(autouse=True)
def _spec_020_init_adapter(request: pytest.FixtureRequest) -> object:
    """Per-test adapter initialization for the default LiteLLM path.

    Resets the active-adapter slot before each test (so SC-005 fail-
    closed tests start clean) and initializes the LiteLLM adapter when
    the env var is unset / explicitly `litellm`. Tests that drive their
    own `initialize_adapter()` (e.g., `test_020_adapter_registry.py`)
    request the marker `no_adapter_autoinit` to skip auto-init.
    """
    from src.api_bridge.adapter import (
        AdapterRegistry,
        _reset_adapter_for_tests,
        initialize_adapter,
    )

    _reset_adapter_for_tests()
    skip_marker = request.node.get_closest_marker("no_adapter_autoinit")
    if skip_marker is None and AdapterRegistry.get("litellm") is not None:
        adapter_name = os.environ.get("SACP_PROVIDER_ADAPTER", "litellm").lower()
        if adapter_name == "litellm":
            with contextlib.suppress(SystemExit):
                initialize_adapter()
    yield
    _reset_adapter_for_tests()


@pytest.fixture(scope="session")
def event_loop_policy() -> object:
    """Use default event loop policy for all async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
async def _create_test_db() -> AsyncGenerator[str, None]:
    """Create a temporary test database, yield URL, then drop it."""
    db_name = f"sacp_test_{uuid.uuid4().hex[:8]}"
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"

    try:
        conn = await asyncpg.connect(admin_url)
    except (OSError, asyncpg.PostgresError):
        pytest.skip("PostgreSQL not reachable — skipping DB tests")

    await conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
    await conn.execute(f"CREATE DATABASE {db_name}")
    await conn.close()

    test_url = TEST_DB_URL.rsplit("/", 1)[0] + f"/{db_name}"
    yield test_url

    conn = await asyncpg.connect(admin_url)
    await conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
    await conn.close()


@pytest.fixture(scope="session")
async def _run_migrations(_create_test_db: str) -> str:
    """Run Alembic migrations on the test database."""
    conn = await asyncpg.connect(_create_test_db)
    try:
        await _apply_schema(conn)
    finally:
        await conn.close()
    return _create_test_db


async def _apply_schema(conn: asyncpg.Connection) -> None:
    """Apply the initial schema directly via raw DDL for test speed."""
    await _execute_schema_sql(conn)


async def _execute_schema_sql(conn: asyncpg.Connection) -> None:
    """Execute raw schema DDL for test database setup."""
    schema_sql = _get_schema_sql()
    for statement in schema_sql:
        if statement.strip():
            await conn.execute(statement)


def _get_schema_sql() -> list[str]:
    """Return the DDL statements for the full schema."""
    return [
        _sessions_ddl(),
        _participants_ddl(),
        _sessions_fk_ddl(),
        _branches_ddl(),
        _messages_ddl(),
        _routing_log_ddl(),
        _usage_log_ddl(),
        _convergence_log_ddl(),
        _admin_audit_log_ddl(),
        _security_events_ddl(),
        _interrupt_queue_ddl(),
        _review_gate_drafts_ddl(),
        _invites_ddl(),
        _proposals_ddl(),
        _votes_ddl(),
        _session_register_ddl(),
        _participant_register_override_ddl(),
        _accounts_ddl(),
        _account_participants_ddl(),
        _compression_log_ddl(),
        _detection_events_ddl(),
        _facilitator_notes_ddl(),
        *_index_ddls(),
    ]


# density_baseline_window REAL[] added in alembic 010 for spec 004 §FR-020 —
# rolling 20-turn density values for in-process anomaly comparison.
# length_cap_* + conclude_phase_started_at + active_seconds_accumulator added
# in alembic 011 for spec 025 FR-001 / FR-002 — opt-in session-length cap and
# durable active-time accumulator. Module-level constant so the schema-mirror
# regex parser (scripts/check_schema_mirror.py) sees all columns in one block.
_SESSIONS_TABLE_DDL = """
    CREATE TABLE sessions (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        status TEXT NOT NULL DEFAULT 'active',
        current_turn INTEGER NOT NULL DEFAULT 0,
        last_summary_turn INTEGER NOT NULL DEFAULT 0,
        facilitator_id TEXT,
        auto_approve BOOLEAN DEFAULT FALSE,
        auto_archive_days INTEGER,
        auto_delete_days INTEGER,
        parent_session_id TEXT,
        cadence_preset TEXT DEFAULT 'cruise',
        complexity_classifier_mode TEXT DEFAULT 'pattern',
        min_model_tier TEXT DEFAULT 'low',
        acceptance_mode TEXT DEFAULT 'unanimous',
        review_gate_pause_scope TEXT NOT NULL DEFAULT 'session'
            CHECK (review_gate_pause_scope IN ('session', 'participant')),
        density_baseline_window REAL[] DEFAULT '{}',
        length_cap_kind TEXT NOT NULL DEFAULT 'none'
            CHECK (length_cap_kind IN ('none', 'time', 'turns', 'both')),
        length_cap_seconds BIGINT
            CHECK (length_cap_seconds IS NULL OR length_cap_seconds BETWEEN 60 AND 2592000),
        length_cap_turns INTEGER
            CHECK (length_cap_turns IS NULL OR length_cap_turns BETWEEN 1 AND 10000),
        conclude_phase_started_at TIMESTAMPTZ,
        active_seconds_accumulator BIGINT
            CHECK (active_seconds_accumulator IS NULL OR active_seconds_accumulator >= 0),
        active_phase_started_at TIMESTAMPTZ,
        compression_mode TEXT NOT NULL DEFAULT 'auto'
            CHECK (compression_mode IN ('auto', 'off', 'noop', 'llmlingua2_mbert',
                                        'selective_context', 'provence', 'layer6'))
    )
"""


def _sessions_ddl() -> str:
    return _SESSIONS_TABLE_DDL


def _participants_ddl() -> str:
    return _PARTICIPANTS_TABLE_DDL


_PARTICIPANTS_TABLE_DDL = """
    CREATE TABLE participants (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        display_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'pending',
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        model_tier TEXT NOT NULL,
        prompt_tier TEXT DEFAULT 'mid',
        model_family TEXT NOT NULL,
        context_window INTEGER NOT NULL,
        supports_tools BOOLEAN DEFAULT TRUE,
        supports_streaming BOOLEAN DEFAULT TRUE,
        domain_tags TEXT NOT NULL DEFAULT '[]',
        routing_preference TEXT DEFAULT 'always',
        observer_interval INTEGER DEFAULT 10,
        burst_interval INTEGER DEFAULT 20,
        review_gate_timeout INTEGER DEFAULT 600,
        turns_since_last_burst INTEGER DEFAULT 0,
        turn_timeout_seconds INTEGER DEFAULT 180,
        consecutive_timeouts INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        budget_hourly REAL,
        budget_daily REAL,
        max_tokens_per_turn INTEGER,
        cost_per_input_token REAL,
        cost_per_output_token REAL,
        system_prompt TEXT NOT NULL DEFAULT '',
        api_endpoint TEXT,
        api_key_encrypted TEXT,
        auth_token_hash TEXT,
        auth_token_lookup TEXT,
        last_seen TIMESTAMP,
        invited_by TEXT REFERENCES participants(id),
        approved_at TIMESTAMP,
        token_expires_at TIMESTAMP,
        bound_ip TEXT,
        wait_mode TEXT NOT NULL DEFAULT 'wait_for_human',
        standby_cycle_count INTEGER NOT NULL DEFAULT 0,
        wait_mode_metadata TEXT NOT NULL DEFAULT '{}'
    )
"""


def _sessions_fk_ddl() -> str:
    return """
        ALTER TABLE sessions
        ADD CONSTRAINT fk_sessions_facilitator
        FOREIGN KEY (facilitator_id) REFERENCES participants(id)
    """


def _branches_ddl() -> str:
    return """
        CREATE TABLE branches (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            parent_branch_id TEXT REFERENCES branches(id),
            branch_point_turn INTEGER NOT NULL DEFAULT 0,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_by TEXT NOT NULL REFERENCES participants(id),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """


def _messages_ddl() -> str:
    return """
        CREATE TABLE messages (
            turn_number INTEGER NOT NULL,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            branch_id TEXT NOT NULL DEFAULT 'main'
                REFERENCES branches(id),
            parent_turn INTEGER,
            speaker_id TEXT NOT NULL REFERENCES participants(id),
            speaker_type TEXT NOT NULL,
            delegated_from TEXT REFERENCES participants(id),
            complexity_score TEXT NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL,
            cost_usd REAL,
            created_at TIMESTAMP DEFAULT NOW(),
            summary_epoch INTEGER,
            PRIMARY KEY (turn_number, session_id, branch_id)
        )
    """


# Per-stage timing columns (route_ms..advisory_lock_wait_ms) added in
# alembic 008 backing 003 §FR-030 / §FR-032 + Constitution §12 V14.
# Five shaping columns (shaping_score_ms..shaping_reason) added in
# alembic 013 backing 021 §FR-011 — all NULL-default for backward
# compatibility (SC-002).
_ROUTING_LOG_TABLE_DDL = """
    CREATE TABLE routing_log (
        id SERIAL PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        turn_number INTEGER NOT NULL,
        intended_participant TEXT NOT NULL
            REFERENCES participants(id),
        actual_participant TEXT NOT NULL
            REFERENCES participants(id),
        routing_action TEXT NOT NULL,
        complexity_score TEXT NOT NULL,
        domain_match BOOLEAN NOT NULL,
        reason TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT NOW(),
        route_ms INTEGER,
        assemble_ms INTEGER,
        dispatch_ms INTEGER,
        persist_ms INTEGER,
        advisory_lock_wait_ms INTEGER,
        shaping_score_ms INTEGER,
        shaping_retry_dispatch_ms INTEGER,
        filler_score NUMERIC(4,3),
        shaping_retry_delta_text TEXT,
        shaping_reason TEXT,
        standby_eval_ms INTEGER,
        pivot_inject_ms INTEGER,
        standby_transition_ms INTEGER
    )
"""


def _routing_log_ddl() -> str:
    return _ROUTING_LOG_TABLE_DDL


def _usage_log_ddl() -> str:
    return """
        CREATE TABLE usage_log (
            id SERIAL PRIMARY KEY,
            participant_id TEXT NOT NULL
                REFERENCES participants(id),
            turn_number INTEGER NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_usd REAL NOT NULL,
            timestamp TIMESTAMP DEFAULT NOW()
        )
    """


def _convergence_log_ddl() -> str:
    # tier + density_value + baseline_value + nullable embedding/similarity
    # added in alembic 010 for spec 004 §FR-020 density-anomaly logging.
    # PK extended to (turn_number, session_id, tier) so convergence and
    # density-anomaly rows coexist on the same turn.
    return """
        CREATE TABLE convergence_log (
            turn_number INTEGER NOT NULL,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            embedding BYTEA,
            similarity_score REAL,
            divergence_prompted BOOLEAN DEFAULT FALSE,
            escalated_to_human BOOLEAN DEFAULT FALSE,
            tier TEXT NOT NULL DEFAULT 'convergence',
            density_value REAL,
            baseline_value REAL,
            PRIMARY KEY (turn_number, session_id, tier)
        )
    """


def _admin_audit_log_ddl() -> str:
    # session_id and facilitator_id are denormalized identifiers (no FK) so
    # audit log rows survive session/participant deletion per 001 FR-019 +
    # US5 §4. Mirror of alembic 007_audit_log_survives_deletion.
    return """
        CREATE TABLE admin_audit_log (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            facilitator_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_id TEXT NOT NULL,
            previous_value TEXT,
            new_value TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        )
    """


def _security_events_ddl() -> str:
    # layer_duration_ms (007 §FR-020) + override_reason / override_actor_id
    # (§4.9 / spec 012 FR-006) added in alembic 008. override_actor_id has
    # no FK to allow audit rows to outlive participant deletion, mirroring
    # the admin_audit_log pattern from alembic 007.
    return """
        CREATE TABLE security_events (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            speaker_id TEXT NOT NULL REFERENCES participants(id),
            turn_number INTEGER NOT NULL,
            layer TEXT NOT NULL,
            risk_score REAL,
            findings TEXT NOT NULL,
            blocked BOOLEAN NOT NULL,
            timestamp TIMESTAMP DEFAULT NOW(),
            layer_duration_ms INTEGER,
            override_reason TEXT,
            override_actor_id TEXT
        )
    """


def _interrupt_queue_ddl() -> str:
    return """
        CREATE TABLE interrupt_queue (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            participant_id TEXT NOT NULL
                REFERENCES participants(id),
            content TEXT NOT NULL,
            priority INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW(),
            delivered_at TIMESTAMP
        )
    """


def _review_gate_drafts_ddl() -> str:
    return """
        CREATE TABLE review_gate_drafts (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            participant_id TEXT NOT NULL
                REFERENCES participants(id),
            turn_number INTEGER NOT NULL,
            draft_content TEXT NOT NULL,
            context_summary TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            edited_content TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            resolved_at TIMESTAMP
        )
    """


def _invites_ddl() -> str:
    return """
        CREATE TABLE invites (
            token_hash TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            created_by TEXT NOT NULL
                REFERENCES participants(id),
            max_uses INTEGER DEFAULT 1,
            uses INTEGER DEFAULT 0,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """


def _proposals_ddl() -> str:
    return """
        CREATE TABLE proposals (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            proposed_by TEXT NOT NULL
                REFERENCES participants(id),
            topic TEXT NOT NULL,
            position TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            acceptance_mode TEXT NOT NULL,
            expires_at TIMESTAMP,
            resolved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """


def _votes_ddl() -> str:
    return """
        CREATE TABLE votes (
            proposal_id TEXT NOT NULL REFERENCES proposals(id),
            participant_id TEXT NOT NULL
                REFERENCES participants(id),
            vote TEXT NOT NULL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (proposal_id, participant_id)
        )
    """


def _session_register_ddl() -> str:
    # Spec 021 alembic 013: one row per session holding the register
    # slider value (1-5). FK on session cascades on session delete
    # (FR-015). FK on facilitator references participants(id) since
    # facilitator is a role on participants — no separate facilitators
    # table exists.
    return """
        CREATE TABLE session_register (
            session_id TEXT PRIMARY KEY
                REFERENCES sessions(id) ON DELETE CASCADE,
            slider_value INTEGER NOT NULL
                CHECK (slider_value BETWEEN 1 AND 5),
            set_by_facilitator_id TEXT NOT NULL
                REFERENCES participants(id),
            last_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """


def _participant_register_override_ddl() -> str:
    # Spec 021 alembic 013: zero-or-one row per participant holding a
    # per-participant override of the session slider. Cascades on
    # participant or session delete (FR-015 / SC-007).
    return """
        CREATE TABLE participant_register_override (
            participant_id TEXT PRIMARY KEY
                REFERENCES participants(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL
                REFERENCES sessions(id) ON DELETE CASCADE,
            slider_value INTEGER NOT NULL
                CHECK (slider_value BETWEEN 1 AND 5),
            set_by_facilitator_id TEXT NOT NULL
                REFERENCES participants(id),
            last_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """


def _accounts_ddl() -> str:
    # Spec 023 alembic 015 + 016: persistent identity layer above per-session
    # tokens. UUID id, lower-cased email (partial unique index covers
    # only pending_verification + active so a deleted-account row coexists
    # with a fresh registration after the grace period — research §2),
    # argon2id-encoded password_hash with empty-string sentinel on
    # deletion, CHECK-constrained status, four timestamp columns plus
    # email_grace_release_at populated at deletion time from
    # SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS. email_hash (alembic 016)
    # is the HMAC of the lowercased email under SACP_AUTH_LOOKUP_KEY;
    # survives deletion so the grace-window lookup can match the deleted
    # row after email is zeroed.
    return """
        CREATE TABLE accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL,
            email_hash TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_verification'
                CHECK (status IN ('pending_verification', 'active', 'deleted')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ,
            deleted_at TIMESTAMPTZ,
            email_grace_release_at TIMESTAMPTZ
        )
    """


def _account_participants_ddl() -> str:
    # Spec 023 alembic 015: zero-or-more join rows binding an account to
    # per-session participant records. account_id FK is ON DELETE RESTRICT
    # (FR-012's preserve-row-on-delete contract); participant_id FK is ON
    # DELETE CASCADE + UNIQUE (FR-002's at-most-one-account-per-participant
    # invariant). The btree index on account_id is the primary lookup for
    # /me/sessions per research.md §9.
    return """
        CREATE TABLE account_participants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL
                REFERENCES accounts(id) ON DELETE RESTRICT,
            participant_id TEXT NOT NULL UNIQUE
                REFERENCES participants(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """


def _compression_log_ddl() -> str:
    # Spec 026 alembic 018: append-only per-dispatch compression telemetry
    # per Session 2026-05-11 §2 + FR-007 + SC-013. One row per
    # CompressorService.compress() invocation including NoOp dispatches.
    # CHECK constraints enforce compressor_id and trust_tier enums + the
    # non-negative numeric invariants. Indexes target session-scoped reads
    # (spec 016 metrics, spec 010 debug export) and layer group-by.
    return """
        CREATE TABLE compression_log (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            participant_id TEXT NOT NULL,
            source_tokens INTEGER NOT NULL CHECK (source_tokens >= 0),
            output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
            compressor_id TEXT NOT NULL
                CHECK (compressor_id IN ('noop', 'llmlingua2_mbert',
                                          'selective_context', 'provence', 'layer6')),
            compressor_version TEXT NOT NULL,
            trust_tier TEXT NOT NULL
                CHECK (trust_tier IN ('system', 'facilitator', 'participant_supplied')),
            layer TEXT NOT NULL,
            duration_ms REAL NOT NULL CHECK (duration_ms >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """


_DETECTION_EVENTS_CLASS_LIST = (
    "'ai_question_opened', 'ai_exit_requested', 'density_anomaly',"
    " 'mode_recommendation', 'mode_change'"
)
_DETECTION_EVENTS_DISPOSITION_LIST = (
    "'pending', 'banner_acknowledged', 'banner_dismissed', 'auto_resolved'"
)


def _detection_events_ddl() -> str:
    """spec 022 — alembic 017 mirror; detection event history persistence."""
    return f"""
        CREATE TABLE detection_events (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            event_class TEXT NOT NULL,
            participant_id TEXT NOT NULL,
            trigger_snippet TEXT,
            detector_score REAL,
            turn_number INTEGER,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            disposition TEXT NOT NULL DEFAULT 'pending',
            last_disposition_change_at TIMESTAMPTZ,
            CONSTRAINT detection_events_class_check
                CHECK (event_class IN ({_DETECTION_EVENTS_CLASS_LIST})),
            CONSTRAINT detection_events_disposition_check
                CHECK (disposition IN ({_DETECTION_EVENTS_DISPOSITION_LIST}))
        )
    """


def _index_ddls() -> list[str]:
    return [
        *_core_index_ddls(),
        *_account_index_ddls(),
        *_compression_log_index_ddls(),
        *_detection_events_index_ddls(),
        *_facilitator_notes_index_ddls(),
    ]


def _compression_log_index_ddls() -> list[str]:
    return [
        "CREATE INDEX compression_log_session_created_idx"
        " ON compression_log (session_id, created_at DESC)",
        "CREATE INDEX compression_log_compressor_created_idx"
        " ON compression_log (compressor_id, created_at DESC)",
    ]


def _detection_events_index_ddls() -> list[str]:
    """spec 022 — alembic 017 mirror; three indexes covering the FR-001 query plan."""
    return [
        "CREATE INDEX detection_events_session_timestamp_idx"
        " ON detection_events (session_id, timestamp DESC)",
        "CREATE INDEX detection_events_session_class_idx"
        " ON detection_events (session_id, event_class)",
        "CREATE INDEX detection_events_session_participant_idx"
        " ON detection_events (session_id, participant_id)",
    ]


def _facilitator_notes_ddl() -> str:
    """spec 024 — alembic 019 mirror; facilitator scratch notes table.

    Operator-private workspace state per FR-001 (NEVER assembled into
    AI context — `tests/test_024_architectural.py` enforces). Three
    partial indexes target the deleted_at IS NULL hot path.
    """
    return """
        CREATE TABLE facilitator_notes (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL
                REFERENCES sessions(id) ON DELETE CASCADE,
            account_id UUID
                REFERENCES accounts(id) ON DELETE SET NULL,
            actor_participant_id TEXT NOT NULL
                REFERENCES participants(id) ON DELETE CASCADE,
            content TEXT NOT NULL CHECK (char_length(content) >= 1),
            version INTEGER NOT NULL DEFAULT 1
                CHECK (version >= 1),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMPTZ,
            promoted_at TIMESTAMPTZ,
            promoted_message_turn INTEGER
        )
    """


def _facilitator_notes_index_ddls() -> list[str]:
    """spec 024 — alembic 019 mirror; three partial indexes covering the FR-002 query plan."""
    return [
        "CREATE INDEX facilitator_notes_session_idx"
        " ON facilitator_notes (session_id) WHERE deleted_at IS NULL",
        "CREATE INDEX facilitator_notes_account_idx"
        " ON facilitator_notes (account_id)"
        " WHERE account_id IS NOT NULL AND deleted_at IS NULL",
        "CREATE INDEX facilitator_notes_session_account_idx"
        " ON facilitator_notes (session_id, account_id) WHERE deleted_at IS NULL",
    ]


def _core_index_ddls() -> list[str]:
    return [
        "CREATE INDEX idx_messages_recent ON messages (session_id, branch_id, turn_number DESC)",
        "CREATE INDEX idx_interrupt_pending"
        " ON interrupt_queue (session_id, status, priority DESC, created_at)",
        "CREATE INDEX idx_routing_session_turn ON routing_log (session_id, turn_number)",
        "CREATE INDEX idx_usage_participant ON usage_log (participant_id, timestamp)",
        "CREATE INDEX idx_participants_session ON participants (session_id, status)",
        "CREATE INDEX idx_participants_auth_token_lookup "
        "ON participants (auth_token_lookup) WHERE auth_token_lookup IS NOT NULL",
        "CREATE INDEX idx_invites_session ON invites (session_id)",
        "CREATE INDEX idx_proposals_session ON proposals (session_id, status)",
        "CREATE INDEX idx_review_gate_pending ON review_gate_drafts (session_id, status)",
        # spec 029 §FR-001 / FR-005 — alembic 013 mirror; covers the audit
        # log viewer endpoint query plan (session_id WHERE + timestamp DESC).
        "CREATE INDEX idx_admin_audit_log_session_timestamp "
        "ON admin_audit_log (session_id, timestamp DESC)",
        "CREATE INDEX participant_register_override_session_idx"
        " ON participant_register_override (session_id)",
    ]


def _account_index_ddls() -> list[str]:
    return [
        # spec 023 §FR-002 / research §9 — alembic 015 mirror; covers the
        # /me/sessions JOIN's primary lookup (account_id WHERE).
        "CREATE UNIQUE INDEX accounts_email_active_uidx"
        " ON accounts (email)"
        " WHERE status IN ('pending_verification', 'active')",
        "CREATE INDEX account_participants_account_idx" " ON account_participants (account_id)",
        # spec 023 FR-013 — alembic 016 mirror; grace-period lookup of
        # deleted rows by HMAC of original email (the email column itself
        # is zeroed at delete time per FR-012).
        "CREATE INDEX accounts_email_hash_grace_idx"
        " ON accounts (email_hash)"
        " WHERE status = 'deleted' AND email_grace_release_at IS NOT NULL",
    ]


@pytest.fixture
async def pool(_run_migrations: str) -> AsyncGenerator[asyncpg.Pool, None]:
    """Provide a connection pool, truncate all tables before each test."""
    p = await asyncpg.create_pool(_run_migrations, min_size=1, max_size=5)
    await _truncate_all(p)
    yield p
    await p.close()


async def _truncate_all(pool: asyncpg.Pool) -> None:
    """Truncate all tables for test isolation."""
    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE votes, proposals, invites,"
            " review_gate_drafts, interrupt_queue,"
            " admin_audit_log, convergence_log,"
            " usage_log, routing_log, detection_events,"
            " session_register, participant_register_override,"
            " account_participants, accounts,"
            " messages, branches"
            " CASCADE"
        )
        await conn.execute("UPDATE sessions SET facilitator_id = NULL")
        await conn.execute("TRUNCATE participants CASCADE")
        await conn.execute("TRUNCATE sessions CASCADE")


@pytest.fixture
async def conn(pool: asyncpg.Pool) -> AsyncGenerator[asyncpg.Connection, None]:
    """Provide a single connection with transaction rollback."""
    async with pool.acquire() as connection:
        tr = connection.transaction()
        await tr.start()
        yield connection
        await tr.rollback()


# ---------------------------------------------------------------------------
# Shared integration-test fixtures
# ---------------------------------------------------------------------------

TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture(scope="session")
def encryption_key() -> str:
    """Provide a valid Fernet encryption key for tests."""
    return TEST_ENCRYPTION_KEY


def _build_fake_response(content: str = "Test AI response") -> object:
    """Build a fake LiteLLM response matching acompletion shape."""
    resp = SimpleNamespace()
    choice = SimpleNamespace(message=SimpleNamespace(content=content))
    resp.choices = [choice]
    resp.usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
    return resp


@pytest.fixture
def mock_litellm() -> AsyncGenerator[SimpleNamespace, None]:
    """Patch litellm.acompletion and completion_cost."""
    import litellm

    fake_resp = _build_fake_response()
    acomp = AsyncMock(return_value=fake_resp)
    cost = MagicMock(return_value=0.001)
    with (
        patch.object(litellm, "acompletion", acomp),
        patch.object(litellm, "completion_cost", cost),
    ):
        yield SimpleNamespace(
            acompletion=acomp,
            completion_cost=cost,
            fake_response=fake_resp,
            build=_build_fake_response,
        )


async def _create_test_session(pool: asyncpg.Pool) -> tuple:
    """Create a session with facilitator and main branch."""
    from src.repositories.session_repo import SessionRepository

    return await SessionRepository(pool).create_session(
        "Integration Test Session",
        facilitator_display_name="Facilitator",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )


async def _add_test_participant(
    pool: asyncpg.Pool,
    session_id: str,
    encryption_key: str,
) -> object:
    """Add an AI participant with an encrypted API key."""
    from src.repositories.participant_repo import ParticipantRepository

    p_repo = ParticipantRepository(pool, encryption_key=encryption_key)
    participant, _ = await p_repo.add_participant(
        session_id=session_id,
        display_name="AI Speaker",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        api_key="test-api-key",
        auth_token=uuid.uuid4().hex,
        auto_approve=True,
    )
    return participant


@pytest.fixture
async def session_with_participant(
    pool: asyncpg.Pool,
    encryption_key: str,
) -> tuple:
    """Create a session with facilitator + AI participant."""
    session, facilitator, branch = await _create_test_session(pool)
    participant = await _add_test_participant(
        pool,
        session.id,
        encryption_key,
    )
    return session, facilitator, participant, branch


# ---------------------------------------------------------------------------
# Per-test FastAPI app instance fixture (spec 012 FR-009 / US7)
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_app() -> object:
    """Per-test fresh MCP FastAPI app instance.

    Each test that touches MCP gets its own app object so middleware
    state (request-id contextvars, rate-limit buckets, CORS config
    overrides via app.state) cannot leak across tests. Closes the
    recurring middleware-state-leak bug class in feature 012 US7
    (FR-009).
    """
    from src.mcp_server.app import create_app

    return create_app()


@pytest.fixture
def web_app() -> object:
    """Per-test fresh Web UI FastAPI app instance. Pairs with mcp_app."""
    from src.web_ui.app import create_web_app

    return create_web_app()


def asgi_client(app: object) -> httpx.AsyncClient:
    """Return an httpx.AsyncClient wired through ASGITransport for ``app``.

    Tests that share an asyncpg pool between the test body and the FastAPI
    handler MUST use this instead of starlette's TestClient. TestClient
    runs the app on a separate event loop via BlockingPortal; an asyncpg
    pool created on the test loop then errors with "another operation is
    in progress" when the handler awaits acquire() on a foreign loop.
    httpx.AsyncClient + ASGITransport runs the handler on the caller's
    loop, so the pool stays single-loop.

    Use as ``async with asgi_client(app) as client: ...``.
    """
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Spec 014 synthetic-signal fixtures (no schema change — DMA reuses existing
# admin_audit_log; per spec 014 tasks.md schema-mirror non-task block).
# Per-signal value injectors let DMA tests drive deterministic trajectories
# without spinning up a real loop / convergence engine / batch scheduler.
# ---------------------------------------------------------------------------


class _SignalFeed:
    """Mutable per-signal value holder used by synthetic SignalSource adapters.

    Tests append values via ``push(value)`` and the adapter's ``sample()``
    pops the next value (or replays the last one if drained, mirroring the
    real adapters' "latest sample" semantic).
    """

    def __init__(self) -> None:
        self._values: list[float | int | None] = []
        self._last: float | int | None = None
        self._available: bool = True

    def push(self, value: float | int | None) -> None:
        """Queue a sample value (or None to simulate unavailability)."""
        self._values.append(value)

    def set_available(self, available: bool) -> None:
        """Override is_available() — used to test signal_source_unavailable emission."""
        self._available = available

    def sample(self) -> float | int | None:
        if self._values:
            self._last = self._values.pop(0)
        return self._last

    def is_available(self) -> bool:
        return self._available and (self._last is not None or bool(self._values))


@pytest.fixture
def dma_signal_feeds() -> dict[str, _SignalFeed]:
    """Four named feeds — one per spec-014 signal source.

    Test usage:
        def test_engage(dma_signal_feeds, monkeypatch):
            monkeypatch.setenv("SACP_DMA_TURN_RATE_THRESHOLD_TPM", "30")
            dma_signal_feeds["turn_rate"].push(42)
            ...
    """
    return {
        "turn_rate": _SignalFeed(),
        "convergence_derivative": _SignalFeed(),
        "queue_depth": _SignalFeed(),
        "density_anomaly": _SignalFeed(),
    }


@pytest.fixture
def dma_synthetic_sources(dma_signal_feeds: dict[str, _SignalFeed]) -> list[object]:
    """Build the four real SignalSource adapters wired to the synthetic feeds.

    Returns a list suitable for ``DmaController(signal_sources=...)``. The
    adapters still consult their real env vars for ``is_configured()`` /
    ``threshold()`` — only the data feed is synthetic. Tests set / unset
    env vars via ``monkeypatch`` to drive the per-signal-independence path.
    """
    from src.orchestrator.dma_signals import (
        ConvergenceDerivativeSignal,
        DensityAnomalySignal,
        QueueDepthSignal,
        TurnRateSignal,
    )

    return [
        TurnRateSignal(sampler=dma_signal_feeds["turn_rate"].sample),
        ConvergenceDerivativeSignal(
            similarity_provider=dma_signal_feeds["convergence_derivative"].sample,
        ),
        QueueDepthSignal(
            depth_sampler=dma_signal_feeds["queue_depth"].sample,
            availability=dma_signal_feeds["queue_depth"].is_available,
        ),
        DensityAnomalySignal(count_sampler=dma_signal_feeds["density_anomaly"].sample),
    ]


@pytest.fixture
def dma_clear_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Strip every spec-014 env var so a test starts in a clean state."""
    for name in (
        "SACP_DMA_TURN_RATE_THRESHOLD_TPM",
        "SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD",
        "SACP_DMA_QUEUE_DEPTH_THRESHOLD",
        "SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD",
        "SACP_DMA_DWELL_TIME_S",
        "SACP_AUTO_MODE_ENABLED",
        "SACP_TOPOLOGY",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class _RecordingEmitter:
    """In-memory ModeEmitter stand-in — captures every audit-event call.

    Tests inspect ``calls`` to assert per-event shape and ordering without
    a real Postgres pool. Each call entry is ``(action, kwargs)``.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def emit_recommendation(self, **kwargs: object) -> None:
        self.calls.append(("mode_recommendation", kwargs))

    async def emit_transition(self, **kwargs: object) -> None:
        self.calls.append(("mode_transition", kwargs))

    async def emit_transition_suppressed(self, **kwargs: object) -> None:
        self.calls.append(("mode_transition_suppressed", kwargs))

    async def emit_decision_cycle_throttled(self, **kwargs: object) -> None:
        self.calls.append(("decision_cycle_throttled", kwargs))

    async def emit_signal_source_unavailable(self, **kwargs: object) -> None:
        self.calls.append(("signal_source_unavailable", kwargs))

    def actions(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.fixture
def dma_recording_emitter() -> _RecordingEmitter:
    """Synthetic emitter that captures every mode_* call for assertions."""
    return _RecordingEmitter()
