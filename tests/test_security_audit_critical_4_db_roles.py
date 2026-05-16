# SPDX-License-Identifier: AGPL-3.0-or-later

"""Audit Critical-4: least-privilege DB roles.

Integration tests that require the four SACP roles to be bootstrapped on
the test database (typically via the compose stack's init script). When
the roles are not present the tests skip rather than fail -- the host
pytest fixture connects as ``sacp_test`` which does not have permission
to bootstrap roles itself.

Two parts:

1. Unit tests for the ``alembic/env.py`` DSN guard introduced by
   Critical-4. Companion validator tests live in
   ``tests/test_config_validators.py``.

2. Integration tests that actually open asyncpg connections under each
   of the four roles and confirm the grant matrix matches the migration.
   Marked with ``pytest.mark.integration`` so the default fast suite
   skips them; CI runs them in the slow tier.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import urllib.parse
from collections.abc import Callable, Iterator
from unittest.mock import MagicMock

import asyncpg
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALEMBIC_ENV_PATH = os.path.join(REPO_ROOT, "alembic", "env.py")


@pytest.fixture
def _restore_env() -> Iterator[None]:
    saved = dict(os.environ)
    try:
        yield
    finally:
        for k in list(os.environ.keys()):
            if k not in saved:
                del os.environ[k]
        for k, v in saved.items():
            os.environ[k] = v


def _load_get_database_url() -> Callable[[], str]:
    """Import ``alembic/env.py`` with a stubbed alembic.context.

    The module's top-level invokes ``run_migrations_offline()`` /
    ``run_migrations_online()`` which only works inside a real alembic
    run; the stub returns ``True`` from ``is_offline_mode`` and supplies
    no-op ``configure`` / ``begin_transaction`` / ``run_migrations`` so
    the body executes harmlessly. Caller is responsible for setting
    ``SACP_DATABASE_URL`` before calling so the top-level invocation
    does not raise; the test sets the env back to its target state
    afterwards.
    """
    stub_context = MagicMock()
    stub_context.is_offline_mode.return_value = True
    stub_context.begin_transaction.return_value.__enter__ = MagicMock()
    stub_context.begin_transaction.return_value.__exit__ = MagicMock()
    sys.modules["alembic"] = MagicMock(context=stub_context)
    sys.modules["alembic.context"] = stub_context

    # Set a safe DSN so the top-level run does not raise.
    os.environ.setdefault("SACP_DATABASE_URL", "postgresql://postgres:pw@localhost:5432/sacp")

    spec = importlib.util.spec_from_file_location("_sacp_alembic_env_under_test", _ALEMBIC_ENV_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = module._get_database_url
    assert callable(fn)
    return fn


# ---------------------------------------------------------------------------
# Alembic env DSN guard (unit; no DB)
# ---------------------------------------------------------------------------


def test_alembic_env_rejects_runtime_role_dsn(_restore_env: None) -> None:
    """alembic/env.py::_get_database_url refuses DSNs pointing at runtime roles."""
    get_dsn = _load_get_database_url()
    os.environ.pop("SACP_DATABASE_URL_MIGRATIONS", None)
    os.environ["SACP_DATABASE_URL"] = "postgresql://sacp_app:pw@localhost:5432/sacp"
    with pytest.raises(OSError, match="runtime role"):
        get_dsn()


def test_alembic_env_prefers_migrations_dsn(_restore_env: None) -> None:
    """When both DSNs are set, _MIGRATIONS wins."""
    get_dsn = _load_get_database_url()
    os.environ["SACP_DATABASE_URL_MIGRATIONS"] = (
        "postgresql://sacp_admin:adminpw@localhost:5432/sacp"
    )
    os.environ["SACP_DATABASE_URL"] = "postgresql://sacp_app:apppw@localhost:5432/sacp"
    assert get_dsn() == os.environ["SACP_DATABASE_URL_MIGRATIONS"]


def test_alembic_env_falls_back_to_database_url(_restore_env: None) -> None:
    """When only SACP_DATABASE_URL is set with a non-runtime role, it is used."""
    get_dsn = _load_get_database_url()
    os.environ.pop("SACP_DATABASE_URL_MIGRATIONS", None)
    os.environ["SACP_DATABASE_URL"] = "postgresql://postgres:rootpw@localhost:5432/sacp"
    assert get_dsn() == os.environ["SACP_DATABASE_URL"]


def test_alembic_env_raises_when_neither_dsn_set(_restore_env: None) -> None:
    get_dsn = _load_get_database_url()
    os.environ.pop("SACP_DATABASE_URL_MIGRATIONS", None)
    os.environ.pop("SACP_DATABASE_URL", None)
    with pytest.raises(OSError, match="Neither.*nor.*set"):
        get_dsn()


def test_migration_026_loads_and_advertises_grant_matrix() -> None:
    """Migration 026 exposes the two table tuples and tags down_revision=025."""
    import importlib.util

    path = os.path.join(REPO_ROOT, "alembic", "versions", "026_grant_least_privilege.py")
    spec = importlib.util.spec_from_file_location("_sacp_migration_026", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "026"
    assert module.down_revision == "025"
    # Spot-check the matrix: every table that lands in chain head before 026
    # appears in exactly one of the two tuples.
    all_tables = set(module.MUTABLE_TABLES) | set(module.APPEND_ONLY_TABLES)
    expected_subset = {
        "sessions",
        "participants",
        "messages",
        "admin_audit_log",
        "security_events",
        "oauth_clients",
        "provider_circuit_open_log",
    }
    assert expected_subset.issubset(all_tables)
    assert not (set(module.MUTABLE_TABLES) & set(module.APPEND_ONLY_TABLES))


# ---------------------------------------------------------------------------
# Integration: actual role bindings on the test database
# ---------------------------------------------------------------------------
#
# These tests require the four SACP roles to be present on the cluster
# that hosts the test database. Skip when they are not -- the host
# pytest fixture connects as `sacp_test` and cannot bootstrap roles
# itself; the compose stack's init script handles that, so these tests
# run in the slow / compose-aware CI tier.


def _dsn_for_role(role: str) -> str | None:
    """Return a DSN connecting as the named SACP role, or None to skip."""
    base = os.environ.get("SACP_TEST_DATABASE_URL")
    if not base:
        return None
    pw = os.environ.get(f"SACP_TEST_{role.upper()}_PASSWORD")
    if not pw:
        return None
    parsed = urllib.parse.urlparse(base)
    netloc = f"{role}:{pw}@{parsed.hostname}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return parsed._replace(netloc=netloc).geturl()


pytestmark_integration = pytest.mark.integration


@pytestmark_integration
@pytest.mark.asyncio
async def test_sacp_app_can_select() -> None:
    dsn = _dsn_for_role("sacp_app")
    if dsn is None:
        pytest.skip("sacp_app integration DSN not configured")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.fetch("SELECT 1")
    finally:
        await conn.close()


@pytestmark_integration
@pytest.mark.asyncio
async def test_sacp_app_cannot_delete_admin_audit_log() -> None:
    dsn = _dsn_for_role("sacp_app")
    if dsn is None:
        pytest.skip("sacp_app integration DSN not configured")
    conn = await asyncpg.connect(dsn)
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM admin_audit_log WHERE 1=0")
    finally:
        await conn.close()


@pytestmark_integration
@pytest.mark.asyncio
async def test_sacp_audit_reader_can_select_but_not_write() -> None:
    dsn = _dsn_for_role("sacp_audit_reader")
    if dsn is None:
        pytest.skip("sacp_audit_reader integration DSN not configured")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.fetch("SELECT 1 FROM admin_audit_log WHERE 1=0")
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO admin_audit_log "
                "(session_id, action, timestamp) "
                "VALUES (gen_random_uuid()::text, 'test', NOW())"
            )
    finally:
        await conn.close()


@pytestmark_integration
@pytest.mark.asyncio
async def test_sacp_cleanup_can_delete_and_audit() -> None:
    dsn = _dsn_for_role("sacp_cleanup")
    if dsn is None:
        pytest.skip("sacp_cleanup integration DSN not configured")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("DELETE FROM admin_audit_log WHERE 1=0")
    finally:
        await conn.close()
