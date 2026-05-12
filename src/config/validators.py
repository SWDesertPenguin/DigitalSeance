# SPDX-License-Identifier: AGPL-3.0-or-later

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

import json
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


def validate_anthropic_cache_ttl() -> ValidationFailure | None:
    """SACP_ANTHROPIC_CACHE_TTL: '5m' or '1h', default '1h'.

    Default is '1h' per the 2026-03-06 silent-default change (Anthropic
    dropped the implicit 1h TTL to 5m without notice; SACP defaults
    explicitly to '1h' so multi-minute session cadence retains hits).
    See spec 003 §FR-033.
    """
    val = os.environ.get("SACP_ANTHROPIC_CACHE_TTL")
    if val is None or val.strip() == "":
        return None
    if val not in ("5m", "1h"):
        return ValidationFailure(
            "SACP_ANTHROPIC_CACHE_TTL",
            f"must be '5m' or '1h'; got {val!r}",
        )
    return None


def validate_caching_enabled() -> ValidationFailure | None:
    """SACP_CACHING_ENABLED: '0' or '1', default '1'. See spec 003 §FR-033."""
    return _validate_bool_enum("SACP_CACHING_ENABLED", default="1")


def validate_density_anomaly_ratio() -> ValidationFailure | None:
    """SACP_DENSITY_ANOMALY_RATIO: float in [1.0, 5.0], default 1.5.

    Spec 004 §FR-020 information-density anomaly threshold (multiplier
    over the rolling 20-turn baseline mean). Values outside the range
    indicate operator confusion (1.0 = always-anomaly; > 5.0 silences
    the signal entirely); refuse to bind.
    """
    val = os.environ.get("SACP_DENSITY_ANOMALY_RATIO")
    if val is None or val.strip() == "":
        return None
    try:
        num = float(val)
    except ValueError:
        return ValidationFailure(
            "SACP_DENSITY_ANOMALY_RATIO",
            f"must be a float; got {val!r}",
        )
    if not 1.0 <= num <= 5.0:
        return ValidationFailure(
            "SACP_DENSITY_ANOMALY_RATIO",
            f"must be in [1.0, 5.0]; got {num}",
        )
    return None


def validate_openai_cache_retention() -> ValidationFailure | None:
    """SACP_OPENAI_CACHE_RETENTION: 'default' or '24h', default 'default'.

    24h activates Extended Prompt Caching only on models in the
    bridge-side allowlist (empty in Phase 1; future work adds
    GPT-5.5+ family on production confirmation). Spec 003 §FR-033.
    """
    val = os.environ.get("SACP_OPENAI_CACHE_RETENTION")
    if val is None or val.strip() == "":
        return None
    if val not in ("default", "24h"):
        return ValidationFailure(
            "SACP_OPENAI_CACHE_RETENTION",
            f"must be 'default' or '24h'; got {val!r}",
        )
    return None


def validate_cache_openai_key_strategy() -> ValidationFailure | None:
    """SACP_CACHE_OPENAI_KEY_STRATEGY: 'session_id' or 'participant_id', default 'session_id'.

    Spec 026 FR-001 OpenAI prompt_cache_key routing strategy. session_id
    keeps a session's per-participant fan-out on the same backend for
    cache hit-rate; participant_id partitions per participant for
    operators who explicitly want that.
    """
    val = os.environ.get("SACP_CACHE_OPENAI_KEY_STRATEGY")
    if val is None or val.strip() == "":
        return None
    if val not in ("session_id", "participant_id"):
        return ValidationFailure(
            "SACP_CACHE_OPENAI_KEY_STRATEGY",
            f"must be 'session_id' or 'participant_id'; got {val!r}",
        )
    return None


def validate_compression_phase2_enabled() -> ValidationFailure | None:
    """SACP_COMPRESSION_PHASE2_ENABLED: 'true' or 'false', default 'false'.

    Spec 026 FR-008 Phase 2 master switch. When false (default), Phase 2
    compressors raise NotImplementedError on dispatch. When true, the
    dispatch path can route to LLMLingua2mBERTCompressor or
    SelectiveContextCompressor.
    """
    val = os.environ.get("SACP_COMPRESSION_PHASE2_ENABLED")
    if val is None or val.strip() == "":
        return None
    if val not in ("true", "false"):
        return ValidationFailure(
            "SACP_COMPRESSION_PHASE2_ENABLED",
            f"must be 'true' or 'false'; got {val!r}",
        )
    return None


def validate_compression_threshold_tokens() -> ValidationFailure | None:
    """SACP_COMPRESSION_THRESHOLD_TOKENS: int in [500, 100000], default 4000.

    Spec 026 FR-016 hard-compression engagement threshold. Below 500
    makes compression overhead dominate any savings; above 100000
    effectively disables compression for all real workloads.
    """
    val = os.environ.get("SACP_COMPRESSION_THRESHOLD_TOKENS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_COMPRESSION_THRESHOLD_TOKENS",
            f"must be an integer; got {val!r}",
        )
    if not 500 <= num <= 100000:
        return ValidationFailure(
            "SACP_COMPRESSION_THRESHOLD_TOKENS",
            f"must be in [500, 100000]; got {num}",
        )
    return None


_COMPRESSOR_IDS = frozenset({"noop", "llmlingua2_mbert", "selective_context", "provence", "layer6"})


def validate_compression_default_compressor() -> ValidationFailure | None:
    """SACP_COMPRESSION_DEFAULT_COMPRESSOR: registered compressor id, default 'noop'.

    Spec 026 FR-006 / FR-007 default compressor selection. Phase 1
    default is noop; Phase 2 cutover is a single env-var change to
    llmlingua2_mbert. Out-of-set exits at startup with the list of
    registered names per contracts/env-vars.md.
    """
    val = os.environ.get("SACP_COMPRESSION_DEFAULT_COMPRESSOR")
    if val is None or val.strip() == "":
        return None
    if val not in _COMPRESSOR_IDS:
        return ValidationFailure(
            "SACP_COMPRESSION_DEFAULT_COMPRESSOR",
            f"must be one of {sorted(_COMPRESSOR_IDS)}; got {val!r}",
        )
    return None


def validate_compression_cross_var_interactions() -> ValidationFailure | None:
    """Spec 026 cross-validator: phase-2 / default-compressor / topology coherence.

    Three rules per contracts/env-vars.md "Cross-validator interaction":
      - phase2=false AND default=llmlingua2_mbert -> ValidationFailure (impossible combo).
      - SACP_TOPOLOGY=7 AND default != noop      -> ValidationFailure (topology gate).
      - phase2=true AND default=noop             -> WARN (suspicious, not fatal).
    """
    default = os.environ.get("SACP_COMPRESSION_DEFAULT_COMPRESSOR", "noop") or "noop"
    phase2 = os.environ.get("SACP_COMPRESSION_PHASE2_ENABLED", "false") or "false"
    topology = os.environ.get("SACP_TOPOLOGY")
    phase2_compressors = {"llmlingua2_mbert", "selective_context"}
    if phase2 == "false" and default in phase2_compressors:
        return ValidationFailure(
            "SACP_COMPRESSION_DEFAULT_COMPRESSOR",
            (
                f"is {default!r} but SACP_COMPRESSION_PHASE2_ENABLED is 'false'; "
                f"set SACP_COMPRESSION_PHASE2_ENABLED=true or pick a Phase 1 default"
            ),
        )
    if topology == "7" and default != "noop":
        return ValidationFailure(
            "SACP_COMPRESSION_DEFAULT_COMPRESSOR",
            (
                f"is {default!r} but SACP_TOPOLOGY=7 supports Layer 1 caching only; "
                f"set SACP_COMPRESSION_DEFAULT_COMPRESSOR=noop on topology 7"
            ),
        )
    return None


def validate_compound_retry_total_max_seconds() -> ValidationFailure | None:
    """SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS: int seconds > 0, default 600. 003 §FR-031."""
    val = os.environ.get("SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS")
    if val is None or val.strip() == "":
        return None
    try:
        num = float(val)
    except ValueError:
        return ValidationFailure(
            "SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS",
            f"must be a number; got {val!r}",
        )
    if num <= 0:
        return ValidationFailure(
            "SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS",
            f"must be > 0; got {num}",
        )
    return None


def validate_security_events_retention_days() -> ValidationFailure | None:
    """SACP_SECURITY_EVENTS_RETENTION_DAYS: positive int, optional. 007 §SC-009."""
    val = os.environ.get("SACP_SECURITY_EVENTS_RETENTION_DAYS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_SECURITY_EVENTS_RETENTION_DAYS",
            f"must be integer; got {val!r}",
        )
    if num <= 0:
        return ValidationFailure(
            "SACP_SECURITY_EVENTS_RETENTION_DAYS",
            f"must be > 0; got {num}",
        )
    return None


def validate_compound_retry_warn_factor() -> ValidationFailure | None:
    """SACP_COMPOUND_RETRY_WARN_FACTOR: float >= 1.0, default 2.0. 003 §FR-031."""
    val = os.environ.get("SACP_COMPOUND_RETRY_WARN_FACTOR")
    if val is None or val.strip() == "":
        return None
    try:
        num = float(val)
    except ValueError:
        return ValidationFailure(
            "SACP_COMPOUND_RETRY_WARN_FACTOR",
            f"must be a float; got {val!r}",
        )
    if num < 1.0:
        return ValidationFailure(
            "SACP_COMPOUND_RETRY_WARN_FACTOR",
            f"must be >= 1.0 (warn must not precede the per-attempt timeout); got {num}",
        )
    return None


def validate_high_traffic_batch_cadence_s() -> ValidationFailure | None:
    """SACP_HIGH_TRAFFIC_BATCH_CADENCE_S: int seconds in [1, 300]. 013 §FR-001 / FR-003."""
    val = os.environ.get("SACP_HIGH_TRAFFIC_BATCH_CADENCE_S")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_HIGH_TRAFFIC_BATCH_CADENCE_S",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 300:
        return ValidationFailure(
            "SACP_HIGH_TRAFFIC_BATCH_CADENCE_S",
            f"must be in [1, 300]; got {num}",
        )
    return None


def validate_convergence_threshold_override() -> ValidationFailure | None:
    """SACP_CONVERGENCE_THRESHOLD_OVERRIDE: float in strict (0.0, 1.0). 013 §FR-005 / FR-007."""
    val = os.environ.get("SACP_CONVERGENCE_THRESHOLD_OVERRIDE")
    if val is None or val.strip() == "":
        return None
    try:
        num = float(val)
    except ValueError:
        return ValidationFailure(
            "SACP_CONVERGENCE_THRESHOLD_OVERRIDE",
            f"must be a float; got {val!r}",
        )
    if not 0.0 < num < 1.0:
        return ValidationFailure(
            "SACP_CONVERGENCE_THRESHOLD_OVERRIDE",
            f"must be in strict (0.0, 1.0); got {num}",
        )
    return None


_OBSERVER_DOWNGRADE_REQUIRED_KEYS = ("participants", "tpm")
_OBSERVER_DOWNGRADE_VALID_KEYS = ("participants", "tpm", "restore_window_s")
_OBSERVER_DOWNGRADE_RANGES = {
    "participants": (2, 10),
    "tpm": (1, 600),
    "restore_window_s": (1, 3600),
}


def validate_observer_downgrade_thresholds() -> ValidationFailure | None:
    """SACP_OBSERVER_DOWNGRADE_THRESHOLDS: composite key:value string. 013 §FR-008-FR-011."""
    raw = os.environ.get("SACP_OBSERVER_DOWNGRADE_THRESHOLDS")
    if raw is None or raw.strip() == "":
        return None
    parsed = _parse_observer_downgrade_value(raw)
    if isinstance(parsed, ValidationFailure):
        return parsed
    return _validate_observer_downgrade_keys(parsed)


def _parse_observer_downgrade_value(raw: str) -> dict[str, int] | ValidationFailure:
    """Parse `participants:N,tpm:N[,restore_window_s:N]` into a dict."""
    parsed: dict[str, int] = {}
    for entry in [e.strip() for e in raw.split(",") if e.strip()]:
        if ":" not in entry:
            return ValidationFailure(
                "SACP_OBSERVER_DOWNGRADE_THRESHOLDS",
                f"entry {entry!r} missing ':' separator (expected key:value)",
            )
        key, _, val = entry.partition(":")
        key = key.strip()
        try:
            parsed[key] = int(val.strip())
        except ValueError:
            return ValidationFailure(
                "SACP_OBSERVER_DOWNGRADE_THRESHOLDS",
                f"entry {entry!r}: value must be integer",
            )
    return parsed


def _validate_observer_downgrade_keys(parsed: dict[str, int]) -> ValidationFailure | None:
    """Check required keys, unknown keys, and per-key ranges."""
    for required in _OBSERVER_DOWNGRADE_REQUIRED_KEYS:
        if required not in parsed:
            return ValidationFailure(
                "SACP_OBSERVER_DOWNGRADE_THRESHOLDS",
                f"missing required key {required!r}",
            )
    for key in parsed:
        if key not in _OBSERVER_DOWNGRADE_VALID_KEYS:
            return ValidationFailure(
                "SACP_OBSERVER_DOWNGRADE_THRESHOLDS",
                f"unknown key {key!r} (valid: {_OBSERVER_DOWNGRADE_VALID_KEYS})",
            )
    for key, value in parsed.items():
        lo, hi = _OBSERVER_DOWNGRADE_RANGES[key]
        if not lo <= value <= hi:
            return ValidationFailure(
                "SACP_OBSERVER_DOWNGRADE_THRESHOLDS",
                f"key {key!r} must be in [{lo}, {hi}]; got {value}",
            )
    return None


def validate_dma_turn_rate_threshold_tpm() -> ValidationFailure | None:
    """SACP_DMA_TURN_RATE_THRESHOLD_TPM: int turns/min in [1, 600]. 014 §FR-003 / FR-004."""
    val = os.environ.get("SACP_DMA_TURN_RATE_THRESHOLD_TPM")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_DMA_TURN_RATE_THRESHOLD_TPM",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 600:
        return ValidationFailure(
            "SACP_DMA_TURN_RATE_THRESHOLD_TPM",
            f"must be in [1, 600]; got {num}",
        )
    return None


def validate_dma_convergence_derivative_threshold() -> ValidationFailure | None:
    """SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD: float in (0.0, 1.0]. 014 §FR-003 / FR-004."""
    val = os.environ.get("SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD")
    if val is None or val.strip() == "":
        return None
    try:
        num = float(val)
    except ValueError:
        return ValidationFailure(
            "SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD",
            f"must be a float; got {val!r}",
        )
    if not 0.0 < num <= 1.0:
        return ValidationFailure(
            "SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD",
            f"must be in (0.0, 1.0]; got {num}",
        )
    return None


def validate_dma_queue_depth_threshold() -> ValidationFailure | None:
    """SACP_DMA_QUEUE_DEPTH_THRESHOLD: int pending msgs in [1, 1000]. 014 §FR-003 / FR-004."""
    val = os.environ.get("SACP_DMA_QUEUE_DEPTH_THRESHOLD")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_DMA_QUEUE_DEPTH_THRESHOLD",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 1000:
        return ValidationFailure(
            "SACP_DMA_QUEUE_DEPTH_THRESHOLD",
            f"must be in [1, 1000]; got {num}",
        )
    return None


def validate_dma_density_anomaly_rate_threshold() -> ValidationFailure | None:
    """SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD: int flags/min in [1, 60]. 014 §FR-003 / FR-004."""
    val = os.environ.get("SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 60:
        return ValidationFailure(
            "SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD",
            f"must be in [1, 60]; got {num}",
        )
    return None


def validate_dma_dwell_time_s() -> ValidationFailure | None:
    """SACP_DMA_DWELL_TIME_S: int seconds in [30, 1800]. 014 §FR-007 / FR-010.

    Unset is allowed in advisory mode; required when SACP_AUTO_MODE_ENABLED=true.
    The cross-validator dependency is enforced by validate_auto_mode_enabled.
    """
    val = os.environ.get("SACP_DMA_DWELL_TIME_S")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_DMA_DWELL_TIME_S",
            f"must be integer; got {val!r}",
        )
    if not 30 <= num <= 1800:
        return ValidationFailure(
            "SACP_DMA_DWELL_TIME_S",
            f"must be in [30, 1800]; got {num}",
        )
    return None


def validate_auto_mode_enabled() -> ValidationFailure | None:
    """SACP_AUTO_MODE_ENABLED: 'true' or 'false' (case-sensitive). 014 §FR-006 / FR-010 / FR-011.

    Unset is treated as 'false' (advisory-only). When 'true', SACP_DMA_DWELL_TIME_S
    MUST also be set (FR-010 cross-validator: auto-apply without dwell is flap-prone).
    """
    val = os.environ.get("SACP_AUTO_MODE_ENABLED")
    if val is None or val.strip() == "":
        return None
    if val not in ("true", "false"):
        return ValidationFailure(
            "SACP_AUTO_MODE_ENABLED",
            f"must be exactly 'true' or 'false' (case-sensitive); got {val!r}",
        )
    if val == "true":
        dwell = os.environ.get("SACP_DMA_DWELL_TIME_S")
        if dwell is None or dwell.strip() == "":
            return ValidationFailure(
                "SACP_AUTO_MODE_ENABLED",
                "auto-apply requires SACP_DMA_DWELL_TIME_S; both vars must be set together",
            )
    return None


def validate_sacp_length_cap_default_kind() -> ValidationFailure | None:
    """SACP_LENGTH_CAP_DEFAULT_KIND enum default 'none'. 025 §FR-024."""
    val = os.environ.get("SACP_LENGTH_CAP_DEFAULT_KIND", "none")
    if val not in ("none", "time", "turns", "both"):
        return ValidationFailure(
            "SACP_LENGTH_CAP_DEFAULT_KIND",
            f"must be one of: none, time, turns, both; got {val!r}",
        )
    return None


def validate_sacp_length_cap_default_seconds() -> ValidationFailure | None:
    """SACP_LENGTH_CAP_DEFAULT_SECONDS: empty OR positive int in [60, 2_592_000]. 025 §FR-024."""
    val = os.environ.get("SACP_LENGTH_CAP_DEFAULT_SECONDS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_LENGTH_CAP_DEFAULT_SECONDS",
            f"must be integer; got {val!r}",
        )
    if not 60 <= num <= 2_592_000:
        return ValidationFailure(
            "SACP_LENGTH_CAP_DEFAULT_SECONDS",
            f"must be in [60, 2_592_000] (1 minute to 30 days); got {num}",
        )
    return None


def validate_sacp_length_cap_default_turns() -> ValidationFailure | None:
    """SACP_LENGTH_CAP_DEFAULT_TURNS: empty OR positive int in [1, 10_000]. 025 §FR-024."""
    val = os.environ.get("SACP_LENGTH_CAP_DEFAULT_TURNS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_LENGTH_CAP_DEFAULT_TURNS",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 10_000:
        return ValidationFailure(
            "SACP_LENGTH_CAP_DEFAULT_TURNS",
            f"must be in [1, 10_000]; got {num}",
        )
    return None


def validate_sacp_conclude_phase_trigger_fraction() -> ValidationFailure | None:
    """SACP_CONCLUDE_PHASE_TRIGGER_FRACTION float in strict (0.0, 1.0). 025 §FR-005."""
    val = os.environ.get("SACP_CONCLUDE_PHASE_TRIGGER_FRACTION")
    if val is None or val.strip() == "":
        return None
    try:
        num = float(val)
    except ValueError:
        return ValidationFailure(
            "SACP_CONCLUDE_PHASE_TRIGGER_FRACTION",
            f"must be a float; got {val!r}",
        )
    if not 0.0 < num < 1.0:
        return ValidationFailure(
            "SACP_CONCLUDE_PHASE_TRIGGER_FRACTION",
            f"must be in strict (0.0, 1.0); got {num}",
        )
    return None


def validate_sacp_conclude_phase_prompt_tier() -> ValidationFailure | None:
    """SACP_CONCLUDE_PHASE_PROMPT_TIER: int in {1, 2, 3, 4}, default 4. 025 §FR-008."""
    val = os.environ.get("SACP_CONCLUDE_PHASE_PROMPT_TIER")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_CONCLUDE_PHASE_PROMPT_TIER",
            f"must be integer; got {val!r}",
        )
    if num not in (1, 2, 3, 4):
        return ValidationFailure(
            "SACP_CONCLUDE_PHASE_PROMPT_TIER",
            f"must be in {{1, 2, 3, 4}}; got {num}",
        )
    return None


def validate_filler_threshold() -> ValidationFailure | None:
    """SACP_FILLER_THRESHOLD: float in [0.0, 1.0]. 021 §FR-002 / FR-004.

    Unset is allowed — per-family default from the BehavioralProfile dict
    in src/orchestrator/shaping.py applies. When set, this env var
    overrides every provider family's default uniformly per research.md §9.
    """
    val = os.environ.get("SACP_FILLER_THRESHOLD")
    if val is None or val.strip() == "":
        return None
    try:
        num = float(val)
    except ValueError:
        return ValidationFailure(
            "SACP_FILLER_THRESHOLD",
            f"must be a float; got {val!r}",
        )
    if not 0.0 <= num <= 1.0:
        return ValidationFailure(
            "SACP_FILLER_THRESHOLD",
            f"must be in [0.0, 1.0]; got {num}",
        )
    return None


def validate_register_default() -> ValidationFailure | None:
    """SACP_REGISTER_DEFAULT: int in {1,2,3,4,5}. 021 §FR-009 / FR-010.

    Default 2 (Conversational) per spec §"Configuration (V16)" — applies
    when no session_register row has been written for a session.
    """
    val = os.environ.get("SACP_REGISTER_DEFAULT")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_REGISTER_DEFAULT",
            f"must be integer; got {val!r}",
        )
    if num not in (1, 2, 3, 4, 5):
        return ValidationFailure(
            "SACP_REGISTER_DEFAULT",
            f"must be in {{1,2,3,4,5}}; got {num}",
        )
    return None


def validate_response_shaping_enabled() -> ValidationFailure | None:
    """SACP_RESPONSE_SHAPING_ENABLED: bool. 021 §FR-005.

    Default false — the master switch ships off so deployments opt in
    explicitly. Accepts 'true'/'false' (case-insensitive) or '1'/'0' per
    existing validator convention.
    """
    val = os.environ.get("SACP_RESPONSE_SHAPING_ENABLED")
    if val is None or val.strip() == "":
        return None
    if val.strip().lower() not in ("true", "false", "1", "0"):
        return ValidationFailure(
            "SACP_RESPONSE_SHAPING_ENABLED",
            f"must be 'true'/'false' (case-insensitive) or '1'/'0'; got {val!r}",
        )
    return None


def validate_network_ratelimit_enabled() -> ValidationFailure | None:
    """SACP_NETWORK_RATELIMIT_ENABLED: bool, default false. 019 §FR-001 / FR-014.

    Master switch for the per-IP network rate limiter. When unset or 'false',
    the middleware is NOT registered and pre-feature behavior is preserved
    byte-identically (SC-006).
    """
    val = os.environ.get("SACP_NETWORK_RATELIMIT_ENABLED")
    if val is None or val.strip() == "":
        return None
    if val.strip().lower() not in ("true", "false", "1", "0"):
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_ENABLED",
            f"must be 'true'/'false' (case-insensitive) or '1'/'0'; got {val!r}",
        )
    return None


def validate_network_ratelimit_rpm() -> ValidationFailure | None:
    """SACP_NETWORK_RATELIMIT_RPM: int [1, 6000], default 60. 019 §FR-003.

    Required when SACP_NETWORK_RATELIMIT_ENABLED=true; the limiter requires a
    budget to be useful. Unset paired with _ENABLED=true causes startup exit
    per the spec's Configuration (V16) section.
    """
    enabled_raw = os.environ.get("SACP_NETWORK_RATELIMIT_ENABLED", "").strip().lower()
    enabled = enabled_raw in ("true", "1")
    val = os.environ.get("SACP_NETWORK_RATELIMIT_RPM")
    if val is None or val.strip() == "":
        if enabled:
            return ValidationFailure(
                "SACP_NETWORK_RATELIMIT_RPM",
                "must be set when SACP_NETWORK_RATELIMIT_ENABLED=true",
            )
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_RPM",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 6000:
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_RPM",
            f"must be in [1, 6000]; got {num}",
        )
    return None


def validate_network_ratelimit_burst() -> ValidationFailure | None:
    """SACP_NETWORK_RATELIMIT_BURST: int [1, 10000], default 15. 019 §FR-003.

    Token-bucket capacity. Allows short bursts above the steady-state RPM.
    Default 15 = 60/4 — quiet-then-active client can spike up to 15 requests
    in a quarter-minute before the steady-state rate kicks in.
    """
    val = os.environ.get("SACP_NETWORK_RATELIMIT_BURST")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_BURST",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 10000:
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_BURST",
            f"must be in [1, 10000]; got {num}",
        )
    return None


def validate_network_ratelimit_trust_forwarded_headers() -> ValidationFailure | None:
    """SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS: bool, default false. 019 §FR-011.

    Trust-by-opt-in for forwarded-header parsing. When false (default), the
    middleware uses the immediate peer IP and ignores Forwarded (RFC 7239) /
    X-Forwarded-For headers. When true, the operator is responsible for
    ensuring the upstream proxy sanitizes inbound headers before forwarding.
    """
    val = os.environ.get("SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS")
    if val is None or val.strip() == "":
        return None
    if val.strip().lower() not in ("true", "false", "1", "0"):
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS",
            f"must be 'true'/'false' (case-insensitive) or '1'/'0'; got {val!r}",
        )
    return None


def validate_network_ratelimit_max_keys() -> ValidationFailure | None:
    """SACP_NETWORK_RATELIMIT_MAX_KEYS: int [1024, 1_000_000], default 100_000. 019 §FR-004.

    LRU bound on the per-IP budget map. When the map exceeds this size, the
    least-recently-accessed entry is evicted. Memory bound is
    MAX_KEYS x ~300 bytes per entry; default 100k = ~30MB worst case.
    """
    val = os.environ.get("SACP_NETWORK_RATELIMIT_MAX_KEYS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_MAX_KEYS",
            f"must be integer; got {val!r}",
        )
    if not 1024 <= num <= 1_000_000:
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_MAX_KEYS",
            f"must be in [1024, 1_000_000]; got {num}",
        )
    return None


# Spec 020 — provider adapter abstraction. The validator hardcodes the
# v1 valid set (`litellm`, `mock`); future adapter specs extend this set
# in their landing PRs per research.md §9. Hardcoding is intentional:
# startup validation runs before adapter packages import (which would
# populate the runtime AdapterRegistry), so the validator cannot consult
# the registry at validation time.
_PROVIDER_ADAPTER_VALID = ("litellm", "mock")


def validate_provider_adapter() -> ValidationFailure | None:
    """SACP_PROVIDER_ADAPTER: adapter name from registry, default 'litellm'.

    Per spec 020 FR-002 / FR-003 / SC-005. Out-of-set values exit at
    startup with an error message listing registered names.
    """
    val = os.environ.get("SACP_PROVIDER_ADAPTER")
    if val is None or val.strip() == "":
        return None
    folded = val.strip().lower()
    if folded not in _PROVIDER_ADAPTER_VALID:
        return ValidationFailure(
            "SACP_PROVIDER_ADAPTER",
            f"must be one of {sorted(_PROVIDER_ADAPTER_VALID)}; got {val!r}",
        )
    return None


_MOCK_PATH_VAR = "SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH"


def validate_provider_adapter_mock_fixtures_path() -> ValidationFailure | None:
    """SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH required + readable when adapter='mock'.

    Cross-validator dependency on SACP_PROVIDER_ADAPTER per spec 020
    FR-006 / FR-007 / SC-004; ignored when adapter is anything else.
    """
    adapter = os.environ.get("SACP_PROVIDER_ADAPTER", "litellm").strip().lower()
    if adapter != "mock":
        return None
    path = os.environ.get(_MOCK_PATH_VAR)
    if path is None or path.strip() == "":
        return ValidationFailure(
            _MOCK_PATH_VAR,
            f"SACP_PROVIDER_ADAPTER=mock requires {_MOCK_PATH_VAR} to be set",
        )
    if not os.path.isfile(path):
        return ValidationFailure(_MOCK_PATH_VAR, f"{path!r} is not a readable file")
    try:
        with open(path, encoding="utf-8") as f:
            json.load(f)
    except json.JSONDecodeError as exc:
        return ValidationFailure(_MOCK_PATH_VAR, f"{path!r} contains invalid JSON: {exc}")
    except OSError as exc:
        return ValidationFailure(_MOCK_PATH_VAR, f"{path!r} could not be read: {exc}")
    return None


def validate_audit_viewer_enabled() -> ValidationFailure | None:
    """SACP_AUDIT_VIEWER_ENABLED: bool, default false. 029 §FR-018.

    Master switch for the human-readable audit log viewer surface. When unset
    or 'false', the GET /tools/admin/audit_log route is NOT mounted and the
    audit_log_appended WS broadcast remains dormant. Accepts 'true'/'false'
    (case-insensitive) or '1'/'0' per the existing validator convention
    (mirrors validate_response_shaping_enabled / validate_network_ratelimit_enabled).
    """
    val = os.environ.get("SACP_AUDIT_VIEWER_ENABLED")
    if val is None or val.strip() == "":
        return None
    if val.strip().lower() not in ("true", "false", "1", "0"):
        return ValidationFailure(
            "SACP_AUDIT_VIEWER_ENABLED",
            f"must be 'true'/'false' (case-insensitive) or '1'/'0'; got {val!r}",
        )
    return None


def validate_audit_viewer_page_size() -> ValidationFailure | None:
    """SACP_AUDIT_VIEWER_PAGE_SIZE: int [10, 500], default 50. 029 §FR-005 / FR-017.

    Caps the ``limit`` query parameter on GET /tools/admin/audit_log. Values
    outside the inclusive range refuse to bind so an operator misconfiguration
    cannot ship an unreasonable page size in production.
    """
    val = os.environ.get("SACP_AUDIT_VIEWER_PAGE_SIZE")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_AUDIT_VIEWER_PAGE_SIZE",
            f"must be integer; got {val!r}",
        )
    if not 10 <= num <= 500:
        return ValidationFailure(
            "SACP_AUDIT_VIEWER_PAGE_SIZE",
            f"must be in [10, 500]; got {num}",
        )
    return None


def validate_audit_viewer_retention_days() -> ValidationFailure | None:
    """SACP_AUDIT_VIEWER_RETENTION_DAYS: empty OR int [1, 36500]. 029 §FR-016 / FR-017.

    Display-only retention cap. Empty (default) means no WHERE clause — the
    viewer renders every audit row for the session. When set, the endpoint
    applies ``WHERE timestamp >= NOW() - INTERVAL 'N days'``. The underlying
    ``admin_audit_log`` table is untouched regardless.
    """
    val = os.environ.get("SACP_AUDIT_VIEWER_RETENTION_DAYS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_AUDIT_VIEWER_RETENTION_DAYS",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 36500:
        return ValidationFailure(
            "SACP_AUDIT_VIEWER_RETENTION_DAYS",
            f"must be in [1, 36500] (1 day to 100 years); got {num}",
        )
    return None


def validate_detection_history_enabled() -> ValidationFailure | None:
    """SACP_DETECTION_HISTORY_ENABLED: bool, default false. 022 §FR-016.

    Master switch for the detection event history panel surface. When unset or
    'false', neither GET /tools/admin/detection_events nor POST .../resurface
    are mounted and the detection_event_appended / detection_event_resurfaced
    WS broadcasts remain dormant. Accepts 'true'/'false' (case-insensitive)
    or '1'/'0' per the existing validator convention.
    """
    val = os.environ.get("SACP_DETECTION_HISTORY_ENABLED")
    if val is None or val.strip() == "":
        return None
    if val.strip().lower() not in ("true", "false", "1", "0"):
        return ValidationFailure(
            "SACP_DETECTION_HISTORY_ENABLED",
            f"must be 'true'/'false' (case-insensitive) or '1'/'0'; got {val!r}",
        )
    return None


def validate_detection_history_max_events() -> ValidationFailure | None:
    """SACP_DETECTION_HISTORY_MAX_EVENTS: empty OR int [1, 100000]. 022 §FR-013.

    Caps the number of detection events returned by the page query. Empty
    (default) means no LIMIT — the endpoint returns all events for the
    session. When set, newest events are kept on cap-hit; older events drop.
    """
    val = os.environ.get("SACP_DETECTION_HISTORY_MAX_EVENTS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_DETECTION_HISTORY_MAX_EVENTS",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 100000:
        return ValidationFailure(
            "SACP_DETECTION_HISTORY_MAX_EVENTS",
            f"must be in [1, 100000]; got {num}",
        )
    return None


def validate_detection_history_retention_days() -> ValidationFailure | None:
    """SACP_DETECTION_HISTORY_RETENTION_DAYS: empty OR int [1, 36500]. 022 §FR-014.

    Display-only retention cap for archived sessions. Empty (default) means
    no WHERE clause — the endpoint renders every event regardless of age.
    When set, the endpoint applies WHERE timestamp >= NOW() - INTERVAL 'N
    days' to archived-session queries. Active-session events are unaffected.
    """
    val = os.environ.get("SACP_DETECTION_HISTORY_RETENTION_DAYS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_DETECTION_HISTORY_RETENTION_DAYS",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 36500:
        return ValidationFailure(
            "SACP_DETECTION_HISTORY_RETENTION_DAYS",
            f"must be in [1, 36500] (1 day to 100 years); got {num}",
        )
    return None


def validate_accounts_enabled() -> ValidationFailure | None:
    """SACP_ACCOUNTS_ENABLED: '0' or '1', default '0'. 023 §FR-018 / FR-022.

    Master switch for the entire account surface. When '0' (default), all
    seven account endpoints + GET /me/sessions return HTTP 404 and the SPA
    falls back to the existing token-paste landing. When '1', the account
    router mounts (subject to SACP_TOPOLOGY != '7' per research.md §12).
    """
    return _validate_bool_enum("SACP_ACCOUNTS_ENABLED")


def validate_password_argon2_time_cost() -> ValidationFailure | None:
    """SACP_PASSWORD_ARGON2_TIME_COST: int in [1, 10], default 2. 023 §FR-003.

    Argon2id time cost (number of iterations). OWASP 2024 password-storage
    cheat-sheet minimum is 2; values below 2 emit an OWASP-floor WARN at
    startup but pass syntactic validation. Above 10 introduces unacceptable
    login latency on commodity hardware.
    """
    val = os.environ.get("SACP_PASSWORD_ARGON2_TIME_COST")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_PASSWORD_ARGON2_TIME_COST",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 10:
        return ValidationFailure(
            "SACP_PASSWORD_ARGON2_TIME_COST",
            f"must be in [1, 10]; got {num}",
        )
    return None


def validate_password_argon2_memory_cost_kb() -> ValidationFailure | None:
    """SACP_PASSWORD_ARGON2_MEMORY_COST_KB: int in [7168, 1048576], default 19456. 023 §FR-003.

    Argon2id memory cost (kilobytes). OWASP 2024 cheat-sheet recommends
    19456 (19 MiB) as the default; values below 7168 (7 MiB) are below the
    audit floor and refuse to bind. Values above 1048576 (1 GiB) risk
    memory exhaustion on small instances.
    """
    val = os.environ.get("SACP_PASSWORD_ARGON2_MEMORY_COST_KB")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_PASSWORD_ARGON2_MEMORY_COST_KB",
            f"must be integer; got {val!r}",
        )
    if not 7168 <= num <= 1048576:
        return ValidationFailure(
            "SACP_PASSWORD_ARGON2_MEMORY_COST_KB",
            f"must be in [7168, 1048576] (7 MiB to 1 GiB); got {num}",
        )
    return None


def validate_account_session_ttl_hours() -> ValidationFailure | None:
    """SACP_ACCOUNT_SESSION_TTL_HOURS: int in [1, 8760], default 168. 023 §FR-017.

    Account login session cookie TTL in hours. Default 168 (7 days);
    operators tightening or loosening the default tune this knob within
    the [1, 8760] envelope (1 hour to 1 year).
    """
    val = os.environ.get("SACP_ACCOUNT_SESSION_TTL_HOURS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_ACCOUNT_SESSION_TTL_HOURS",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 8760:
        return ValidationFailure(
            "SACP_ACCOUNT_SESSION_TTL_HOURS",
            f"must be in [1, 8760] (1 hour to 1 year); got {num}",
        )
    return None


def validate_account_rate_limit_per_ip_per_min() -> ValidationFailure | None:
    """SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN: int in [1, 1000], default 10. 023 §FR-015.

    Per-IP rate limit threshold for /tools/account/login and
    /tools/account/create. Separate state container from spec 019's
    middleware (clarify Q10 — additive composition, no shared state).
    Below 1 disables the limiter (rejected); above 1000 the limiter is
    essentially absent.
    """
    val = os.environ.get("SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN",
            f"must be integer; got {val!r}",
        )
    if not 1 <= num <= 1000:
        return ValidationFailure(
            "SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN",
            f"must be in [1, 1000]; got {num}",
        )
    return None


_EMAIL_TRANSPORT_VALID = ("noop", "smtp", "ses", "sendgrid")


def validate_email_transport() -> ValidationFailure | None:
    """SACP_EMAIL_TRANSPORT: enum noop|smtp|ses|sendgrid, default noop. 023 §FR-022.

    Selects the EmailTransport adapter at startup. v1 ships only the
    'noop' adapter; the other three values pass syntactic validation here
    but the adapter factory raises NotImplementedError at startup with a
    clear pointer to specs/023-user-accounts/contracts/email-transport.md
    (research.md §4, §6). Operators needing real transport defer enabling
    accounts until the follow-up email-transport spec ships.
    """
    val = os.environ.get("SACP_EMAIL_TRANSPORT")
    if val is None or val.strip() == "":
        return None
    if val not in _EMAIL_TRANSPORT_VALID:
        return ValidationFailure(
            "SACP_EMAIL_TRANSPORT",
            f"must be one of {list(_EMAIL_TRANSPORT_VALID)}; got {val!r}",
        )
    return None


def validate_account_deletion_email_grace_days() -> ValidationFailure | None:
    """SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS: int in [0, 365], default 7. 023 §FR-013.

    Reserves a deleted account's email address for re-registration during
    the configured window. The value 0 disables the grace period entirely
    (immediate email release on deletion). 365 caps the maximum reservation
    window at one year. Read at deletion time to populate
    accounts.email_grace_release_at.
    """
    val = os.environ.get("SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS",
            f"must be integer; got {val!r}",
        )
    if not 0 <= num <= 365:
        return ValidationFailure(
            "SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS",
            f"must be in [0, 365]; got {num}",
        )
    return None


def validate_deployment_owner_key() -> ValidationFailure | None:
    """SACP_DEPLOYMENT_OWNER_KEY: optional admin shim for spec 023 FR-020.

    When unset/empty, the ownership-transfer endpoint refuses every
    request (no owner key configured → no admin path). When set, the
    value MUST be at least 32 chars of high-entropy randomness — the
    same hygiene as SACP_WEB_UI_COOKIE_KEY. Callers attach
    ``X-Deployment-Owner-Key`` matching this value to authorize the
    transfer.
    """
    val = os.environ.get("SACP_DEPLOYMENT_OWNER_KEY")
    if val is None or val == "":
        return None
    placeholder = _contains_placeholder(val)
    if placeholder:
        return ValidationFailure(
            "SACP_DEPLOYMENT_OWNER_KEY",
            f"contains placeholder {placeholder!r} -- generate a real random secret",
        )
    if len(val) < 32:
        return ValidationFailure(
            "SACP_DEPLOYMENT_OWNER_KEY",
            f"must be >= 32 chars of high-entropy randomness; got {len(val)} chars",
        )
    return None


_STANDBY_WAIT_MODE_VALID = ("wait_for_human", "always")


def validate_standby_default_wait_mode() -> ValidationFailure | None:
    """SACP_STANDBY_DEFAULT_WAIT_MODE: enum, default 'wait_for_human'. 027 §FR-001 / FR-028.

    Two-value enum applied to newly-INSERTed participant rows when the
    facilitator has not set wait_mode explicitly. Out-of-set values exit
    at startup with the list of valid names.
    """
    val = os.environ.get("SACP_STANDBY_DEFAULT_WAIT_MODE")
    if val is None or val.strip() == "":
        return None
    if val not in _STANDBY_WAIT_MODE_VALID:
        return ValidationFailure(
            "SACP_STANDBY_DEFAULT_WAIT_MODE",
            f"must be one of {list(_STANDBY_WAIT_MODE_VALID)}; got {val!r}",
        )
    return None


def validate_standby_filler_detection_turns() -> ValidationFailure | None:
    """SACP_STANDBY_FILLER_DETECTION_TURNS: int in [2, 100], default 5. 027 §FR-017.

    Number of consecutive standby cycles before the auto-pivot fires.
    Below 2 makes the repetition guard meaningless (a single cycle would
    trigger); above 100 makes the pivot effectively unreachable in any
    realistic session.
    """
    val = os.environ.get("SACP_STANDBY_FILLER_DETECTION_TURNS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_STANDBY_FILLER_DETECTION_TURNS",
            f"must be integer; got {val!r}",
        )
    if not 2 <= num <= 100:
        return ValidationFailure(
            "SACP_STANDBY_FILLER_DETECTION_TURNS",
            f"must be in [2, 100]; got {num}",
        )
    return None


def validate_standby_pivot_timeout_seconds() -> ValidationFailure | None:
    """SACP_STANDBY_PIVOT_TIMEOUT_SECONDS: int seconds in [60, 86400], default 600. 027 §FR-017.

    Minimum elapsed time since the gating event opened before the pivot
    can fire. 60s floor prevents racing the gate clear; 86400s ceiling
    (1 day) caps the maximum wait at one human-business-cycle.
    """
    val = os.environ.get("SACP_STANDBY_PIVOT_TIMEOUT_SECONDS")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_STANDBY_PIVOT_TIMEOUT_SECONDS",
            f"must be integer; got {val!r}",
        )
    if not 60 <= num <= 86400:
        return ValidationFailure(
            "SACP_STANDBY_PIVOT_TIMEOUT_SECONDS",
            f"must be in [60, 86400] (1 minute to 1 day); got {num}",
        )
    return None


def validate_standby_pivot_rate_cap_per_session() -> ValidationFailure | None:
    """SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION: int in [0, 100], default 1. 027 §FR-019.

    Per-session pivot cap. 0 disables auto-pivot entirely (operators who
    want pure standby with no orchestrator intervention). 100 caps the
    upper end at a value no realistic session needs.
    """
    val = os.environ.get("SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION")
    if val is None or val.strip() == "":
        return None
    try:
        num = int(val)
    except ValueError:
        return ValidationFailure(
            "SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION",
            f"must be integer; got {val!r}",
        )
    if not 0 <= num <= 100:
        return ValidationFailure(
            "SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION",
            f"must be in [0, 100]; got {num}",
        )
    return None


def validate_web_ui_cookie_key() -> ValidationFailure | None:
    """SACP_WEB_UI_COOKIE_KEY: required signing key for Web UI session cookies.

    Distinct from SACP_ENCRYPTION_KEY so a leak of the at-rest API-key
    encryption key does not also let an attacker forge session cookies,
    and vice-versa. Audit M-02 closes the prior reuse.
    """
    val = os.environ.get("SACP_WEB_UI_COOKIE_KEY")
    if not val:
        return ValidationFailure("SACP_WEB_UI_COOKIE_KEY", "required but not set")
    placeholder = _contains_placeholder(val)
    if placeholder:
        return ValidationFailure(
            "SACP_WEB_UI_COOKIE_KEY",
            f"contains placeholder {placeholder!r} -- generate a real random secret",
        )
    if len(val) < 32:
        return ValidationFailure(
            "SACP_WEB_UI_COOKIE_KEY",
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
    validate_anthropic_cache_ttl,
    validate_caching_enabled,
    validate_density_anomaly_ratio,
    validate_cache_openai_key_strategy,
    validate_compression_phase2_enabled,
    validate_compression_threshold_tokens,
    validate_compression_default_compressor,
    validate_compression_cross_var_interactions,
    validate_openai_cache_retention,
    validate_web_ui_cookie_key,
    validate_compound_retry_total_max_seconds,
    validate_compound_retry_warn_factor,
    validate_security_events_retention_days,
    validate_high_traffic_batch_cadence_s,
    validate_convergence_threshold_override,
    validate_observer_downgrade_thresholds,
    validate_dma_turn_rate_threshold_tpm,
    validate_dma_convergence_derivative_threshold,
    validate_dma_queue_depth_threshold,
    validate_dma_density_anomaly_rate_threshold,
    validate_dma_dwell_time_s,
    validate_auto_mode_enabled,
    validate_sacp_length_cap_default_kind,
    validate_sacp_length_cap_default_seconds,
    validate_sacp_length_cap_default_turns,
    validate_sacp_conclude_phase_trigger_fraction,
    validate_sacp_conclude_phase_prompt_tier,
    validate_filler_threshold,
    validate_register_default,
    validate_response_shaping_enabled,
    validate_network_ratelimit_enabled,
    validate_network_ratelimit_rpm,
    validate_network_ratelimit_burst,
    validate_network_ratelimit_trust_forwarded_headers,
    validate_network_ratelimit_max_keys,
    validate_provider_adapter,
    validate_provider_adapter_mock_fixtures_path,
    validate_audit_viewer_enabled,
    validate_audit_viewer_page_size,
    validate_audit_viewer_retention_days,
    validate_detection_history_enabled,
    validate_detection_history_max_events,
    validate_detection_history_retention_days,
    validate_accounts_enabled,
    validate_password_argon2_time_cost,
    validate_password_argon2_memory_cost_kb,
    validate_account_session_ttl_hours,
    validate_account_rate_limit_per_ip_per_min,
    validate_email_transport,
    validate_account_deletion_email_grace_days,
    validate_deployment_owner_key,
    validate_standby_default_wait_mode,
    validate_standby_filler_detection_turns,
    validate_standby_pivot_timeout_seconds,
    validate_standby_pivot_rate_cap_per_session,
)


def iter_failures() -> Iterator[ValidationFailure]:
    """Run every validator; yield each failure."""
    for validator in VALIDATORS:
        result = validator()
        if result is not None:
            yield result
