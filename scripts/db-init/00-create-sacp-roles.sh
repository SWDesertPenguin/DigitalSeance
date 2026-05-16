#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Bootstrap the SACP least-privilege roles on first cluster init.
#
# This script is mounted into the official Postgres image at
# /docker-entrypoint-initdb.d/00-create-sacp-roles.sh. The image runs every
# *.sh under that directory exactly once, the first time the data volume is
# initialized, against the database named in POSTGRES_DB. Subsequent
# container restarts do NOT re-run init scripts; per-table grants land via
# alembic migration 026 instead.
#
# The script is idempotent on its own (CREATE-or-ALTER ROLE pattern) so it
# is safe to invoke via `psql -f` for a manual re-run after a password
# rotation. Run as `psql -v ON_ERROR_STOP=1 -U $POSTGRES_USER -d $POSTGRES_DB
# -f 00-create-sacp-roles.sh` if you need to rerun without recreating the
# volume.
#
# Audit Critical-4: the deployment path previously connected as the
# bootstrap superuser, rendering src/database/roles.sql inert. This script
# is the authoritative role-creation surface; the SQL file remains as a
# reference but is no longer expected to be executed by deployment.

set -euo pipefail

require_env() {
    local name="$1"
    if [ -z "${!name:-}" ]; then
        echo "Init script error: $name must be set in the postgres service environment." >&2
        echo "See docs/env-vars.md 'Role bootstrap secrets' for the four required passwords." >&2
        exit 1
    fi
}

require_env SACP_ADMIN_PASSWORD
require_env SACP_APP_PASSWORD
require_env SACP_CLEANUP_PASSWORD
require_env SACP_AUDIT_READER_PASSWORD
require_env POSTGRES_DB
require_env POSTGRES_USER

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sacp_admin') THEN
            CREATE ROLE sacp_admin WITH LOGIN ENCRYPTED PASSWORD '${SACP_ADMIN_PASSWORD}';
        ELSE
            ALTER ROLE sacp_admin WITH LOGIN ENCRYPTED PASSWORD '${SACP_ADMIN_PASSWORD}';
        END IF;
    END
    \$\$;

    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sacp_app') THEN
            CREATE ROLE sacp_app WITH LOGIN ENCRYPTED PASSWORD '${SACP_APP_PASSWORD}';
        ELSE
            ALTER ROLE sacp_app WITH LOGIN ENCRYPTED PASSWORD '${SACP_APP_PASSWORD}';
        END IF;
    END
    \$\$;

    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sacp_cleanup') THEN
            CREATE ROLE sacp_cleanup WITH LOGIN ENCRYPTED PASSWORD '${SACP_CLEANUP_PASSWORD}';
        ELSE
            ALTER ROLE sacp_cleanup WITH LOGIN ENCRYPTED PASSWORD '${SACP_CLEANUP_PASSWORD}';
        END IF;
    END
    \$\$;

    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sacp_audit_reader') THEN
            CREATE ROLE sacp_audit_reader WITH LOGIN ENCRYPTED PASSWORD '${SACP_AUDIT_READER_PASSWORD}';
        ELSE
            ALTER ROLE sacp_audit_reader WITH LOGIN ENCRYPTED PASSWORD '${SACP_AUDIT_READER_PASSWORD}';
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO sacp_admin;
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO sacp_app;
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO sacp_cleanup;
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO sacp_audit_reader;

    -- sacp_admin owns the schema so future per-migration DDL inherits its
    -- ownership without separate ALTER OWNER calls.
    ALTER SCHEMA public OWNER TO sacp_admin;
    GRANT ALL ON SCHEMA public TO sacp_admin;

    GRANT USAGE ON SCHEMA public TO sacp_app;
    GRANT USAGE ON SCHEMA public TO sacp_cleanup;
    GRANT USAGE ON SCHEMA public TO sacp_audit_reader;

    -- Default privileges: any future tables CREATEd by sacp_admin (which is
    -- the schema owner so alembic migrations running as sacp_admin pick this
    -- up) automatically grant the per-role baseline below. Per-table grants
    -- still ship in alembic 026 for the existing 25 tables.
    ALTER DEFAULT PRIVILEGES FOR ROLE sacp_admin IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sacp_app;
    ALTER DEFAULT PRIVILEGES FOR ROLE sacp_admin IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO sacp_app;
    ALTER DEFAULT PRIVILEGES FOR ROLE sacp_admin IN SCHEMA public
        GRANT SELECT ON TABLES TO sacp_audit_reader;
    ALTER DEFAULT PRIVILEGES FOR ROLE sacp_admin IN SCHEMA public
        GRANT SELECT, DELETE ON TABLES TO sacp_cleanup;
    ALTER DEFAULT PRIVILEGES FOR ROLE sacp_admin IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO sacp_cleanup;

    -- Final audit echo. Passwords are not logged; this just confirms the
    -- four roles exist after the init heredoc closes.
    SELECT rolname, rolcanlogin
    FROM pg_roles
    WHERE rolname IN ('sacp_admin', 'sacp_app', 'sacp_cleanup', 'sacp_audit_reader')
    ORDER BY rolname;
EOSQL
