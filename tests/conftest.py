"""Shared pytest fixtures for SACP database tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
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
        *_index_ddls(),
    ]


def _sessions_ddl() -> str:
    return """
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
                CHECK (review_gate_pause_scope IN ('session', 'participant'))
        )
    """


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
        last_seen TIMESTAMP,
        invited_by TEXT REFERENCES participants(id),
        approved_at TIMESTAMP,
        token_expires_at TIMESTAMP,
        bound_ip TEXT
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


def _routing_log_ddl() -> str:
    # Per-stage timing columns (route_ms..advisory_lock_wait_ms) added in
    # alembic 008 backing 003 §FR-030 / §FR-032 + Constitution §12 V14.
    return """
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
            advisory_lock_wait_ms INTEGER
        )
    """


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
    return """
        CREATE TABLE convergence_log (
            turn_number INTEGER NOT NULL,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            embedding BYTEA NOT NULL,
            similarity_score REAL NOT NULL,
            divergence_prompted BOOLEAN DEFAULT FALSE,
            escalated_to_human BOOLEAN DEFAULT FALSE,
            PRIMARY KEY (turn_number, session_id)
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


def _index_ddls() -> list[str]:
    return [
        "CREATE INDEX idx_messages_recent ON messages (session_id, branch_id, turn_number DESC)",
        "CREATE INDEX idx_interrupt_pending"
        " ON interrupt_queue (session_id, status, priority DESC, created_at)",
        "CREATE INDEX idx_routing_session_turn ON routing_log (session_id, turn_number)",
        "CREATE INDEX idx_usage_participant ON usage_log (participant_id, timestamp)",
        "CREATE INDEX idx_participants_session ON participants (session_id, status)",
        "CREATE INDEX idx_invites_session ON invites (session_id)",
        "CREATE INDEX idx_proposals_session ON proposals (session_id, status)",
        "CREATE INDEX idx_review_gate_pending ON review_gate_drafts (session_id, status)",
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
            " usage_log, routing_log,"
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
