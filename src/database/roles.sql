-- SACP Database Role Setup
--
-- REFERENCE ONLY -- as of audit Critical-4 the authoritative role
-- bootstrap is `scripts/db-init/00-create-sacp-roles.sh` (mounted into
-- the postgres image at /docker-entrypoint-initdb.d/) and per-table
-- grants ship in alembic migration 026. This file is retained so the
-- bare GRANT vocabulary can be code-reviewed in one place without
-- threading through the shell heredoc + the migration; it is no longer
-- expected to be executed by deployment.
--
-- The schema below is also stale relative to the post-001 chain --
-- newer tables (security_events, session_register, accounts, oauth_*,
-- detection_events, compression_log, facilitator_notes, provider_*
-- audit logs, etc.) are covered by alembic 026's per-table grant list,
-- not by this file. Treat any drift between this file and migration
-- 026 as the migration being canonical.
--
-- Constitution §6.2: Append-only log tables restricted to INSERT and SELECT.

-- Application role (normal operations).
-- Placeholder password trips the V16 startup validator (audit H-04) when
-- inherited via `SACP_DATABASE_URL`. Replace before running this script.
CREATE ROLE sacp_app WITH LOGIN ENCRYPTED PASSWORD 'REPLACE_ME_BEFORE_FIRST_RUN_APP';
GRANT CONNECT ON DATABASE sacp TO sacp_app;
GRANT USAGE ON SCHEMA public TO sacp_app;

-- Full CRUD on mutable tables
GRANT SELECT, INSERT, UPDATE, DELETE ON
    sessions, participants, branches,
    interrupt_queue, review_gate_drafts,
    invites, proposals
TO sacp_app;

-- Append-only: INSERT + SELECT only on immutable tables
GRANT SELECT, INSERT ON
    messages, routing_log, usage_log,
    convergence_log, admin_audit_log, votes
TO sacp_app;

-- Sequence access for SERIAL columns
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sacp_app;

-- Cleanup role (session deletion only). Same placeholder rule as sacp_app.
CREATE ROLE sacp_cleanup WITH LOGIN ENCRYPTED PASSWORD 'REPLACE_ME_BEFORE_FIRST_RUN_CLEANUP';
GRANT CONNECT ON DATABASE sacp TO sacp_cleanup;
GRANT USAGE ON SCHEMA public TO sacp_cleanup;
GRANT SELECT, DELETE ON ALL TABLES IN SCHEMA public TO sacp_cleanup;
GRANT INSERT ON admin_audit_log TO sacp_cleanup;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sacp_cleanup;
