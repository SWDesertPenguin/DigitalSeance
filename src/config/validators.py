"""V16 startup validators for every actually-consumed SACP_* env var.

Per Constitution §12 V16: every SACP_* env var MUST have a documented
type, valid range, and fail-closed semantics. The application validates
every var at startup BEFORE binding any port; an invalid value MUST cause
the process to exit with a clear error rather than silently accepting an
out-of-range default.

Inventory scope: vars actually read by application code (10 entries below).
Documented-but-unwired vars (SACP_RATE_LIMIT_PER_MIN, SACP_DEFAULT_TURN_TIMEOUT)
are listed in `docs/env-vars.md` as Reserved with Phase 3 triggers; they
get no validators here until application code starts consuming them.

Per spec 012 FR-004 / contracts/config-validator-cli.md.
"""

from __future__ import annotations

import os
import urllib.parse
from collections.abc import Callable, Iterator
from typing import NamedTuple


class ValidationFailure(NamedTuple):
    """One env-var validation failure."""

    var_name: str
    reason: str


class ConfigValidationError(Exception):
    """Raised when one or more SACP_* env vars fail validation at startup."""

    def __init__(self, failures: list[ValidationFailure]) -> None:
        self.failures = failures
        body = "\n".join(f"  {f.var_name}: {f.reason}" for f in failures)
        super().__init__(f"config validation failed:\n{body}")


# Strings that mean "operator forgot to replace the placeholder before first
# run". An exact substring match (case-insensitive) on any required-secret
# value triggers a refuse-to-bind. Audit H-04: a copy of `.env.example`
# directly to `.env` shipped a postgres password of literally `changeme`.
_PLACEHOLDER_PATTERNS = (
    "changeme",
    "REPLACE_ME_BEFORE_FIRST_RUN",
    "generate-with-python-fernet",
)


def _contains_placeholder(value: str) -> str | None:
    """Return the matching placeholder pattern, or None if value is clean."""
    lowered = value.lower()
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.lower() in lowered:
            return pattern
    return None


def _validate_bool_enum(name: str, default: str = "0") -> ValidationFailure | None:
    """Bool-style env var: must be '0' or '1'."""
    val = os.environ.get(name, default)
    if val not in ("0", "1"):
        return ValidationFailure(name, f"must be '0' or '1'; got {val!r}")
    return None


def _validate_url(name: str, *, required: bool = False) -> ValidationFailure | None:
    """Single-URL env var. Allowed schemes: http, https, ws, wss."""
    val = os.environ.get(name)
    if not val:
        if required:
            return ValidationFailure(name, "required but not set")
        return None
    parsed = urllib.parse.urlparse(val)
    if parsed.scheme not in ("http", "https", "ws", "wss"):
        return ValidationFailure(name, f"unsupported scheme {parsed.scheme!r}")
    if not parsed.netloc:
        return ValidationFailure(name, f"missing host in {val!r}")
    return None


def _validate_url_list(name: str) -> ValidationFailure | None:
    """Comma-separated URL list. Empty / unset is OK; entries must parse."""
    val = os.environ.get(name, "")
    for entry in [e.strip() for e in val.split(",") if e.strip()]:
        parsed = urllib.parse.urlparse(entry)
        if parsed.scheme not in ("http", "https", "ws", "wss"):
            return ValidationFailure(name, f"entry {entry!r}: unsupported scheme")
        if not parsed.netloc:
            return ValidationFailure(name, f"entry {entry!r}: missing host")
    return None


def validate_database_url() -> ValidationFailure | None:
    """SACP_DATABASE_URL must be a postgresql:// URL with no placeholder secrets."""
    val = os.environ.get("SACP_DATABASE_URL")
    if not val:
        return ValidationFailure("SACP_DATABASE_URL", "required but not set")
    parsed = urllib.parse.urlparse(val)
    if parsed.scheme not in ("postgresql", "postgres"):
        return ValidationFailure(
            "SACP_DATABASE_URL",
            f"must be postgresql:// URL; got scheme {parsed.scheme!r}",
        )
    if not parsed.netloc:
        return ValidationFailure("SACP_DATABASE_URL", "missing host")
    placeholder = _contains_placeholder(val)
    if placeholder:
        return ValidationFailure(
            "SACP_DATABASE_URL",
            f"contains placeholder {placeholder!r} — replace with a real secret",
        )
    return None


def validate_encryption_key() -> ValidationFailure | None:
    """SACP_ENCRYPTION_KEY must decode as a Fernet key (44-char base64) and not be a placeholder."""
    val = os.environ.get("SACP_ENCRYPTION_KEY")
    if not val:
        return ValidationFailure("SACP_ENCRYPTION_KEY", "required but not set")
    placeholder = _contains_placeholder(val)
    if placeholder:
        return ValidationFailure(
            "SACP_ENCRYPTION_KEY",
            f"contains placeholder {placeholder!r} — generate a real Fernet key",
        )
    if len(val) != 44:
        return ValidationFailure(
            "SACP_ENCRYPTION_KEY",
            f"must be 44-char Fernet key; got {len(val)} chars",
        )
    try:
        from cryptography.fernet import Fernet

        Fernet(val.encode())
    except (ValueError, TypeError) as exc:
        return ValidationFailure("SACP_ENCRYPTION_KEY", f"not a valid Fernet key: {exc}")
    return None


def validate_context_max_turns() -> ValidationFailure | None:
    """SACP_CONTEXT_MAX_TURNS: int >= 3 (MVC floor), default 20."""
    val = os.environ.get("SACP_CONTEXT_MAX_TURNS")
    if val is None:
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure("SACP_CONTEXT_MAX_TURNS", f"must be integer; got {val!r}")
    if num < 3:
        return ValidationFailure("SACP_CONTEXT_MAX_TURNS", f"must be >= 3 (MVC floor); got {num}")
    return None


def validate_trust_proxy() -> ValidationFailure | None:
    """SACP_TRUST_PROXY: '0' or '1', default '0'."""
    return _validate_bool_enum("SACP_TRUST_PROXY")


def validate_enable_docs() -> ValidationFailure | None:
    """SACP_ENABLE_DOCS: '0' or '1', default '0'."""
    return _validate_bool_enum("SACP_ENABLE_DOCS")


def validate_web_ui_insecure_cookies() -> ValidationFailure | None:
    """SACP_WEB_UI_INSECURE_COOKIES: '0' or '1', default '0'."""
    return _validate_bool_enum("SACP_WEB_UI_INSECURE_COOKIES")


def validate_web_ui_mcp_origin() -> ValidationFailure | None:
    """SACP_WEB_UI_MCP_ORIGIN: optional URL pointing at the MCP server."""
    return _validate_url("SACP_WEB_UI_MCP_ORIGIN")


def validate_web_ui_ws_origin() -> ValidationFailure | None:
    """SACP_WEB_UI_WS_ORIGIN: optional WebSocket origin."""
    return _validate_url("SACP_WEB_UI_WS_ORIGIN")


def validate_cors_origins() -> ValidationFailure | None:
    """SACP_CORS_ORIGINS: comma-separated URL list."""
    return _validate_url_list("SACP_CORS_ORIGINS")


def validate_web_ui_allowed_origins() -> ValidationFailure | None:
    """SACP_WEB_UI_ALLOWED_ORIGINS: comma-separated URL list."""
    return _validate_url_list("SACP_WEB_UI_ALLOWED_ORIGINS")


def validate_ws_max_connections_per_ip() -> ValidationFailure | None:
    """SACP_WS_MAX_CONNECTIONS_PER_IP: positive int, default 10. Audit H-03."""
    val = os.environ.get("SACP_WS_MAX_CONNECTIONS_PER_IP")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_WS_MAX_CONNECTIONS_PER_IP",
            f"must be integer; got {val!r}",
        )
    if num <= 0:
        return ValidationFailure(
            "SACP_WS_MAX_CONNECTIONS_PER_IP",
            f"must be > 0; got {num}",
        )
    return None


def validate_max_subscribers_per_session() -> ValidationFailure | None:
    """SACP_MAX_SUBSCRIBERS_PER_SESSION: positive int, default 64. 006 §FR-019."""
    val = os.environ.get("SACP_MAX_SUBSCRIBERS_PER_SESSION")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_MAX_SUBSCRIBERS_PER_SESSION",
            f"must be integer; got {val!r}",
        )
    if num <= 0:
        return ValidationFailure(
            "SACP_MAX_SUBSCRIBERS_PER_SESSION",
            f"must be > 0; got {num}",
        )
    return None


def validate_auth_lookup_key() -> ValidationFailure | None:
    """SACP_AUTH_LOOKUP_KEY: required HMAC key for the token-lookup index. Audit C-02."""
    val = os.environ.get("SACP_AUTH_LOOKUP_KEY")
    if not val:
        return ValidationFailure("SACP_AUTH_LOOKUP_KEY", "required but not set")
    placeholder = _contains_placeholder(val)
    if placeholder:
        return ValidationFailure(
            "SACP_AUTH_LOOKUP_KEY",
            f"contains placeholder {placeholder!r} -- generate a real random secret",
        )
    if len(val) < 32:
        return ValidationFailure(
            "SACP_AUTH_LOOKUP_KEY",
            f"must be >= 32 chars of high-entropy randomness; got {len(val)} chars",
        )
    return None


VALIDATORS: tuple[Callable[[], ValidationFailure | None], ...] = (
    validate_database_url,
    validate_encryption_key,
    validate_context_max_turns,
    validate_trust_proxy,
    validate_enable_docs,
    validate_web_ui_insecure_cookies,
    validate_web_ui_mcp_origin,
    validate_web_ui_ws_origin,
    validate_cors_origins,
    validate_web_ui_allowed_origins,
    validate_ws_max_connections_per_ip,
    validate_max_subscribers_per_session,
    validate_auth_lookup_key,
)


def iter_failures() -> Iterator[ValidationFailure]:
    """Run every validator; yield each failure."""
    for validator in VALIDATORS:
        result = validator()
        if result is not None:
            yield result
