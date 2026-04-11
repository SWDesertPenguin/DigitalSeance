-- SACP Database Role Setup
-- Run once per database to configure application-level access control.
-- Constitution §6.2: Append-only log tables restricted to INSERT and SELECT.

-- Application role (normal operations)
CREATE ROLE sacp_app WITH LOGIN ENCRYPTED PASSWORD 'changeme_app';
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

-- Cleanup role (session deletion only)
CREATE ROLE sacp_cleanup WITH LOGIN ENCRYPTED PASSWORD 'changeme_cleanup';
GRANT CONNECT ON DATABASE sacp TO sacp_cleanup;
GRANT USAGE ON SCHEMA public TO sacp_cleanup;
GRANT SELECT, DELETE ON ALL TABLES IN SCHEMA public TO sacp_cleanup;
GRANT INSERT ON admin_audit_log TO sacp_cleanup;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sacp_cleanup;
