# Database role bootstrap and rotation

Operator runbook for the four SACP database roles introduced by audit Critical-4 (`sacp_admin`, `sacp_app`, `sacp_cleanup`, `sacp_audit_reader`). Covers first-time bootstrap, password rotation, failure-mode triage, and the break-glass `POSTGRES_USER` escape.

## Background

Before audit Critical-4, the orchestrator runtime connected to PostgreSQL as the cluster bootstrap superuser (`POSTGRES_USER`, typically `sacp`). Every code path -- application turns, retention sweeps, ad-hoc auditor queries -- ran with full DDL privileges, leaving `src/database/roles.sql` as a documented design that the deployment path silently bypassed. Critical-4 finalizes the role design end-to-end:

| Role | Login | Privileges | Consumer |
| --- | --- | --- | --- |
| `sacp_admin` | yes | Schema owner; runs alembic | `sacp-migrate` one-shot service |
| `sacp_app` | yes | SELECT/INSERT/UPDATE/DELETE on mutable tables; SELECT/INSERT only on append-only logs | `sacp` runtime container |
| `sacp_cleanup` | yes | SELECT/DELETE on every table; INSERT on `admin_audit_log` + `security_events` | Retention sweep scripts |
| `sacp_audit_reader` | yes | SELECT on every table | Out-of-band forensic queries |

Per-role grants land in two places:

- `scripts/db-init/00-create-sacp-roles.sh` -- creates the roles and sets default privileges on the public schema. Mounted at `/docker-entrypoint-initdb.d/00-create-sacp-roles.sh` on the postgres container. Runs once when the data volume is first initialized.
- `alembic/versions/026_grant_least_privilege.py` -- grants per-table SELECT/INSERT/UPDATE/DELETE on the 25 tables that exist at chain head when 026 ships. Runs as part of `alembic upgrade head` via the `sacp-migrate` one-shot service.

## First-time bootstrap

1. Set the four passwords in `.env`:
   - `SACP_ADMIN_PASSWORD=<high-entropy>`
   - `SACP_APP_PASSWORD=<high-entropy>`
   - `SACP_CLEANUP_PASSWORD=<high-entropy>`
   - `SACP_AUDIT_READER_PASSWORD=<high-entropy>`

2. Point `SACP_DATABASE_URL` at `sacp_app`:
   - `SACP_DATABASE_URL=postgresql://sacp_app:<same as SACP_APP_PASSWORD>@localhost:5432/sacp`

3. Bring the stack up: `docker compose up -d`. Expected sequence:
   - `postgres` becomes healthy. On first init the data volume is created; the init script creates the four roles.
   - `sacp-migrate` runs `alembic upgrade head` as `sacp_admin`, applies migration 026 (per-table grants).
   - `sacp` waits on `sacp-migrate` via `service_completed_successfully`, then starts as `sacp_app`.

4. Confirm the roles exist:
   ```
   docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\du"
   ```
   Four rows for `sacp_admin`, `sacp_app`, `sacp_cleanup`, `sacp_audit_reader` -- plus the bootstrap `POSTGRES_USER` superuser, which remains for break-glass access.

## Password rotation

Done in-place against the running cluster -- no downtime required if you stage the rotation correctly.

1. Generate new passwords. Update `.env` first; do NOT restart anything yet.

2. Connect as the bootstrap superuser to apply the new passwords:
   ```
   docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB <<'SQL'
       ALTER ROLE sacp_admin     WITH ENCRYPTED PASSWORD '<new admin>';
       ALTER ROLE sacp_app       WITH ENCRYPTED PASSWORD '<new app>';
       ALTER ROLE sacp_cleanup   WITH ENCRYPTED PASSWORD '<new cleanup>';
       ALTER ROLE sacp_audit_reader WITH ENCRYPTED PASSWORD '<new audit>';
   SQL
   ```

3. Restart the orchestrator to pick up the new `SACP_APP_PASSWORD`:
   ```
   docker compose up -d sacp
   ```

4. Retention sweeps that use `SACP_DATABASE_URL_CLEANUP` will pick up the new password on their next cron tick.

## Failure-mode triage

### "config validation failed: SACP_DATABASE_URL: username must be 'sacp_app'"

The orchestrator's V16 validator refused to bind because `SACP_DATABASE_URL` points at the wrong role. Inspect the env var; if you are running locally without role bootstrap, set `SACP_DEV_MODE=1`. In any deployment serving real users, this is a misconfiguration -- the runtime DSN MUST point at `sacp_app`.

### "Migration DSN points at runtime role 'sacp_app'"

`alembic/env.py` refused to run migrations under a runtime role. Either set `SACP_DATABASE_URL_MIGRATIONS` to a `sacp_admin` DSN, or unset both DSNs and re-run via the `sacp-migrate` service so the compose stack supplies the elevated DSN automatically.

### "InsufficientPrivilege: permission denied for table <X>" from the orchestrator

A newer table was added by a recent migration but the per-table grants for the runtime roles were not extended. Two paths:

1. Preferred: open a migration that issues the missing grants and ship it.
2. Hot-patch (operator workstation, NOT a script): connect as `sacp_admin` and run the missing grant manually. Capture the SQL into a follow-up migration so the fix survives the next cluster init.

### `sacp-migrate` exits non-zero

Read the container logs: `docker compose logs sacp-migrate`. Most common causes:

- `SACP_ADMIN_PASSWORD` mismatch between the postgres init env and the compose `sacp-migrate` env (rotated one without the other).
- Migration emitted SQL that requires DDL beyond what `sacp_admin` holds. Audit the migration; `sacp_admin` is the schema owner and should be able to run any standard DDL, so this is rare and usually indicates a migration trying to `CREATE EXTENSION` or otherwise touch cluster-level state.

## Break-glass: `POSTGRES_USER`

The bootstrap superuser remains in place for two reasons:

1. The init script itself runs as `POSTGRES_USER` -- removing it would break first-init.
2. Operators need a route to ALTER passwords / inspect role state when one of the four roles is locked out.

Any use of `POSTGRES_USER` in the deployment owner key audit trail (per `docs/env-vars.md` SACP_DEPLOYMENT_OWNER_KEY) MUST be logged with rationale. Routine application work under `POSTGRES_USER` is the pre-Critical-4 vulnerability and should be treated as a regression.

## Recovery: rebuilding the roles on an existing volume

The init script only runs on first volume init. If the roles get dropped accidentally (e.g. an operator ran a destructive cleanup) on a long-lived volume, the init script will NOT re-run on its own. Recovery path:

1. As `POSTGRES_USER`, source the init script directly:
   ```
   docker compose exec -e SACP_ADMIN_PASSWORD=... -e SACP_APP_PASSWORD=... \
       -e SACP_CLEANUP_PASSWORD=... -e SACP_AUDIT_READER_PASSWORD=... \
       postgres bash /docker-entrypoint-initdb.d/00-create-sacp-roles.sh
   ```
   The script is idempotent (CREATE-or-ALTER) so re-running it is safe.

2. Re-run `alembic upgrade head` from the `sacp-migrate` service. Migration 026's GRANTs are additive; running them against roles that already hold the privilege is a no-op.

3. Restart `sacp` once the migrate service exits 0.
