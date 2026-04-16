"""001: Initial SACP schema — 13 core tables.

Revision ID: 001
Create Date: 2026-04-11
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all 13 core tables with constraints and indexes."""
    _create_sessions()
    _create_participants()
    _create_branches()
    _create_messages()
    _create_routing_log()
    _create_usage_log()
    _create_convergence_log()
    _create_admin_audit_log()
    _create_interrupt_queue()
    _create_review_gate_drafts()
    _create_invites()
    _create_proposals()
    _create_votes()
    _create_indexes()


def _create_sessions() -> None:
    op.execute("""
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
            acceptance_mode TEXT DEFAULT 'unanimous'
        )
    """)


def _create_participants() -> None:
    op.execute(_PARTICIPANTS_DDL)
    _add_facilitator_fk()


def _add_facilitator_fk() -> None:
    """Add deferred FK from sessions.facilitator_id to participants."""
    op.execute("""
        ALTER TABLE sessions
        ADD CONSTRAINT fk_sessions_facilitator
        FOREIGN KEY (facilitator_id) REFERENCES participants(id)
    """)


_PARTICIPANTS_DDL = """
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
        turn_timeout_seconds INTEGER DEFAULT 60,
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
        approved_at TIMESTAMP
    )
"""


def _create_branches() -> None:
    op.execute("""
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
    """)


def _create_messages() -> None:
    op.execute("""
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
    """)


def _create_routing_log() -> None:
    op.execute("""
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
            timestamp TIMESTAMP DEFAULT NOW()
        )
    """)


def _create_usage_log() -> None:
    op.execute("""
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
    """)


def _create_convergence_log() -> None:
    op.execute("""
        CREATE TABLE convergence_log (
            turn_number INTEGER NOT NULL,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            embedding BYTEA NOT NULL,
            similarity_score REAL NOT NULL,
            divergence_prompted BOOLEAN DEFAULT FALSE,
            escalated_to_human BOOLEAN DEFAULT FALSE,
            PRIMARY KEY (turn_number, session_id)
        )
    """)


def _create_admin_audit_log() -> None:
    op.execute("""
        CREATE TABLE admin_audit_log (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            facilitator_id TEXT NOT NULL
                REFERENCES participants(id),
            action TEXT NOT NULL,
            target_id TEXT NOT NULL,
            previous_value TEXT,
            new_value TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        )
    """)


def _create_interrupt_queue() -> None:
    op.execute("""
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
    """)


def _create_review_gate_drafts() -> None:
    op.execute("""
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
    """)


def _create_invites() -> None:
    op.execute("""
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
    """)


def _create_proposals() -> None:
    op.execute("""
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
    """)


def _create_votes() -> None:
    op.execute("""
        CREATE TABLE votes (
            proposal_id TEXT NOT NULL REFERENCES proposals(id),
            participant_id TEXT NOT NULL
                REFERENCES participants(id),
            vote TEXT NOT NULL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (proposal_id, participant_id)
        )
    """)


def _create_indexes() -> None:
    """Create hot-path indexes for prepared statement queries."""
    for ddl in _INDEX_DDLS:
        op.execute(ddl)


_INDEX_DDLS = [
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


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    tables = [
        "votes",
        "proposals",
        "invites",
        "review_gate_drafts",
        "interrupt_queue",
        "admin_audit_log",
        "convergence_log",
        "usage_log",
        "routing_log",
        "messages",
        "branches",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    # Drop FK before participants
    op.execute("""
        ALTER TABLE sessions
        DROP CONSTRAINT IF EXISTS fk_sessions_facilitator
    """)
    op.execute("DROP TABLE IF EXISTS participants CASCADE")
    op.execute("DROP TABLE IF EXISTS sessions CASCADE")
