"""Meta-tests for V16 startup config validation (spec 012 FR-004).

Verifies src.config.validators + src.run_apps.--validate-config-only
behave per contracts/config-validator-cli.md:
- happy path: valid env → exit 0 with success line
- single invalid: process exits 1; failing var named in stderr
- multiple invalid: ALL failing vars reported in a single run
- required vars missing → fail-closed
- bool/url/int validators each reject their respective bad inputs
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

REPO_ROOT = Path(__file__).resolve().parent.parent

# Generated per process so no committable Fernet-shaped string lives in the tree.
_VALID_FERNET = Fernet.generate_key().decode()
_VALID_DB = "postgresql://user:pass@localhost:5432/db"


def _valid_env() -> dict[str, str]:
    """Minimum env that passes every validator."""
    return {
        "SACP_DATABASE_URL": _VALID_DB,
        "SACP_ENCRYPTION_KEY": _VALID_FERNET,
    }


def _run(env: dict[str, str], *extra_args: str) -> subprocess.CompletedProcess[str]:
    # S603: input is sys.executable + a fixed module path; env is test-controlled.
    # Strip SACP_* from inherited environ before layering test env on top so
    # the test dict is the EXACT spec of which SACP_* vars are set. CI
    # workflows set SACP_DATABASE_URL etc. at the job level; without this
    # filter, popping a var from `env` doesn't actually remove it from the
    # subprocess (the workflow-level value bleeds back through). Locally
    # this was masked because the dev shell didn't export those vars.
    base_env = {k: v for k, v in os.environ.items() if not k.startswith("SACP_")}
    full_env = {**base_env, **env}
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "src.run_apps", *extra_args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=full_env,
    )


def test_validate_only_happy_path():
    result = _run(_valid_env(), "--validate-config-only")
    assert result.returncode == 0, result.stderr
    assert "config validation: OK" in result.stdout


def test_validate_only_missing_required():
    """SACP_DATABASE_URL absent → exit 1 with var name in stderr."""
    env = _valid_env()
    env.pop("SACP_DATABASE_URL")
    result = _run(env, "--validate-config-only")
    assert result.returncode == 1
    assert "SACP_DATABASE_URL" in result.stderr
    assert "config validation: FAIL" in result.stdout


def test_multiple_invalid_all_reported():
    """Three bad values → all three named in stderr in single run."""
    env = _valid_env()
    env["SACP_TRUST_PROXY"] = "2"
    env["SACP_ENABLE_DOCS"] = "yes"
    env["SACP_CONTEXT_MAX_TURNS"] = "1"
    result = _run(env, "--validate-config-only")
    assert result.returncode == 1
    assert "SACP_TRUST_PROXY" in result.stderr
    assert "SACP_ENABLE_DOCS" in result.stderr
    assert "SACP_CONTEXT_MAX_TURNS" in result.stderr


@pytest.fixture
def _restore_env() -> Iterator[None]:
    """Snapshot SACP_* env on entry, restore on exit."""
    saved = {k: v for k, v in os.environ.items() if k.startswith("SACP_")}
    yield
    for key in [k for k in os.environ if k.startswith("SACP_")]:
        del os.environ[key]
    os.environ.update(saved)


def test_bool_validator_rejects_non_bool_string(_restore_env: None):
    from src.config.validators import validate_trust_proxy

    os.environ["SACP_TRUST_PROXY"] = "true"
    failure = validate_trust_proxy()
    assert failure is not None
    assert failure.var_name == "SACP_TRUST_PROXY"
    assert "must be '0' or '1'" in failure.reason


def test_int_validator_rejects_below_floor(_restore_env: None):
    from src.config.validators import validate_context_max_turns

    os.environ["SACP_CONTEXT_MAX_TURNS"] = "2"
    failure = validate_context_max_turns()
    assert failure is not None
    assert failure.var_name == "SACP_CONTEXT_MAX_TURNS"
    assert "must be >= 3" in failure.reason


def test_int_validator_rejects_non_integer(_restore_env: None):
    from src.config.validators import validate_context_max_turns

    os.environ["SACP_CONTEXT_MAX_TURNS"] = "twenty"
    failure = validate_context_max_turns()
    assert failure is not None
    assert "must be integer" in failure.reason


def test_url_validator_rejects_bad_scheme(_restore_env: None):
    from src.config.validators import validate_web_ui_mcp_origin

    os.environ["SACP_WEB_UI_MCP_ORIGIN"] = "ftp://example.com"
    failure = validate_web_ui_mcp_origin()
    assert failure is not None
    assert "unsupported scheme" in failure.reason


def test_url_list_validator_accepts_empty(_restore_env: None):
    from src.config.validators import validate_cors_origins

    os.environ["SACP_CORS_ORIGINS"] = ""
    assert validate_cors_origins() is None


def test_url_list_validator_rejects_bad_entry(_restore_env: None):
    from src.config.validators import validate_cors_origins

    os.environ["SACP_CORS_ORIGINS"] = "https://ok.example,not a url"
    failure = validate_cors_origins()
    assert failure is not None
    assert "missing host" in failure.reason or "unsupported scheme" in failure.reason


def test_database_url_rejects_non_postgres(_restore_env: None):
    from src.config.validators import validate_database_url

    os.environ["SACP_DATABASE_URL"] = "mysql://user:pass@localhost/db"
    failure = validate_database_url()
    assert failure is not None
    assert "postgresql" in failure.reason


def test_encryption_key_rejects_short(_restore_env: None):
    from src.config.validators import validate_encryption_key

    os.environ["SACP_ENCRYPTION_KEY"] = "tooshort"
    failure = validate_encryption_key()
    assert failure is not None
    assert "44-char" in failure.reason


def test_validate_all_raises_with_all_failures(_restore_env: None):
    from src.config import ConfigValidationError, validate_all

    os.environ["SACP_DATABASE_URL"] = ""
    os.environ["SACP_ENCRYPTION_KEY"] = "tooshort"
    os.environ["SACP_TRUST_PROXY"] = "yes"
    with pytest.raises(ConfigValidationError) as exc_info:
        validate_all()
    var_names = {f.var_name for f in exc_info.value.failures}
    assert "SACP_DATABASE_URL" in var_names
    assert "SACP_ENCRYPTION_KEY" in var_names
    assert "SACP_TRUST_PROXY" in var_names


def test_database_url_rejects_changeme_placeholder(_restore_env: None):
    """Audit H-04: literal `changeme` in the URL trips the validator."""
    from src.config.validators import validate_database_url

    os.environ["SACP_DATABASE_URL"] = "postgresql://sacp:changeme@localhost:5432/sacp"
    failure = validate_database_url()
    assert failure is not None
    assert failure.var_name == "SACP_DATABASE_URL"
    assert "placeholder" in failure.reason
    assert "changeme" in failure.reason


def test_database_url_rejects_replace_me_placeholder(_restore_env: None):
    """Audit H-04: REPLACE_ME_BEFORE_FIRST_RUN canonical placeholder also trips."""
    from src.config.validators import validate_database_url

    os.environ["SACP_DATABASE_URL"] = (
        "postgresql://sacp:REPLACE_ME_BEFORE_FIRST_RUN@localhost:5432/sacp"
    )
    failure = validate_database_url()
    assert failure is not None
    assert "placeholder" in failure.reason
    assert "REPLACE_ME_BEFORE_FIRST_RUN" in failure.reason


def test_encryption_key_rejects_generate_placeholder(_restore_env: None):
    """Audit H-04: the literal `.env.example` Fernet placeholder trips before length check."""
    from src.config.validators import validate_encryption_key

    os.environ["SACP_ENCRYPTION_KEY"] = "generate-with-python-fernet"
    failure = validate_encryption_key()
    assert failure is not None
    assert "placeholder" in failure.reason
    # Placeholder check fires BEFORE length check — the operator gets the
    # actionable message ("replace with a real Fernet key") instead of the
    # misleading "must be 44-char" error.
    assert "44-char" not in failure.reason


def test_encryption_key_rejects_replace_me_placeholder(_restore_env: None):
    from src.config.validators import validate_encryption_key

    os.environ["SACP_ENCRYPTION_KEY"] = "REPLACE_ME_BEFORE_FIRST_RUN"
    failure = validate_encryption_key()
    assert failure is not None
    assert "placeholder" in failure.reason


def test_database_url_accepts_real_credentials(_restore_env: None):
    """Sanity check: a non-placeholder URL passes."""
    from src.config.validators import validate_database_url

    os.environ["SACP_DATABASE_URL"] = "postgresql://user:realpassword@localhost:5432/sacp"
    assert validate_database_url() is None


def test_encryption_key_accepts_real_fernet(_restore_env: None):
    """Sanity check: a real Fernet key passes."""
    from cryptography.fernet import Fernet

    from src.config.validators import validate_encryption_key

    os.environ["SACP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    assert validate_encryption_key() is None
