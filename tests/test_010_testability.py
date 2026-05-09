# SPDX-License-Identifier: AGPL-3.0-or-later

"""010 debug-export testability suite (Phase F, fix/010-followups).

Covers audit-plan items not addressed by ``test_mcp_app.py`` /
``test_mcp_e2e.py``:

* FR-7 secret-name pattern: env vars matching the secret-suffix regex are
  dropped from the config snapshot even if added to the allowlist
* SC-008 embedding strip: convergence_log subdump never carries the
  embedding BYTEA column (column-list-not-SELECT-* invariant)
* FR-5 empty collections: a session with no logs/interrupts/messages
  serializes those as `[]`, not omitted, not null
* FR-6 / SC-007 read-only: only the FR-8 admin_audit_log row is permitted
  to write during an export — the data-fetch surface is read-only
* FR-9 strip-list contents pinned: every required sensitive field is in
  ``_SENSITIVE_FIELDS`` (paired with the existing CI heuristic guard)
* `_jsonify` byte-placeholder format: bytes serialize to ``<N bytes>``
  rather than leaking raw bytes / base64
"""

from __future__ import annotations

import inspect
import os
import re

from src.mcp_server.tools import debug as debug_module
from src.mcp_server.tools.debug import (
    _CONFIG_KEYS,
    _LOG_QUERIES,
    _SECRET_NAME_PATTERN,
    _SENSITIVE_FIELDS,
    _config_snapshot,
    _jsonify,
    _scrub,
)

# ---------------------------------------------------------------------------
# FR-7: secret-name pattern guard on config snapshot
# ---------------------------------------------------------------------------


def test_fr7_secret_name_pattern_matches_documented_suffixes() -> None:
    """Pattern catches every documented secret-suffix shape."""
    cases = [
        "SACP_FOO_KEY",
        "SACP_FOO_SECRET",
        "SACP_FOO_TOKEN",
        "SACP_FOO_PASSWORD",
        "SACP_FOO_CREDENTIAL",
        "SACP_FOO_PASSPHRASE",
        # Case-insensitive per re.IGNORECASE flag on _SECRET_NAME_PATTERN.
        "sacp_foo_key",
        "SACP_FOO_secret",
    ]
    for name in cases:
        assert _SECRET_NAME_PATTERN.search(name) is not None, f"{name} should be flagged secret"


def test_fr7_secret_name_pattern_does_not_match_benign_keys() -> None:
    """Benign env vars in the documented allowlist are NOT flagged."""
    benign = [
        "SACP_CONTEXT_MAX_TURNS",
        "SACP_CORS_ORIGINS",
        "SACP_DEFAULT_TURN_TIMEOUT",
        "SACP_RATE_LIMIT_PER_MIN",
    ]
    for name in benign:
        assert (
            _SECRET_NAME_PATTERN.search(name) is None
        ), f"{name} false-positive — pattern would drop a benign var"


def test_fr7_config_snapshot_drops_allowlisted_secret_named_var(
    monkeypatch,
) -> None:
    """If a secret-suffixed key were added to the allowlist, it is dropped.

    Defense-in-depth: the allowlist is the primary surface, but the
    secret-name pattern catches operator naming mistakes (someone adds
    ``SACP_PROVIDER_KEY`` to ``_CONFIG_KEYS`` thinking it's a model name).
    """
    monkeypatch.setattr(
        debug_module,
        "_CONFIG_KEYS",
        ("SACP_CONTEXT_MAX_TURNS", "SACP_FOO_KEY"),
    )
    monkeypatch.setenv("SACP_CONTEXT_MAX_TURNS", "20")
    monkeypatch.setenv("SACP_FOO_KEY", "leaked-secret-must-not-appear")
    snapshot = _config_snapshot()
    assert "SACP_CONTEXT_MAX_TURNS" in snapshot
    assert "SACP_FOO_KEY" not in snapshot
    assert "leaked-secret-must-not-appear" not in repr(snapshot)


def test_fr7_config_snapshot_returns_only_documented_keys(monkeypatch) -> None:
    """Snapshot keys are a subset of `_CONFIG_KEYS` minus the secret-pattern hits."""
    for k in _CONFIG_KEYS:
        monkeypatch.setenv(k, f"value-of-{k}")
    snapshot = _config_snapshot()
    assert set(snapshot).issubset(set(_CONFIG_KEYS))
    for forbidden in os.environ:
        if forbidden not in _CONFIG_KEYS:
            assert forbidden not in snapshot


# ---------------------------------------------------------------------------
# SC-008: embedding strip — convergence_log subdump never includes embedding
# ---------------------------------------------------------------------------


def test_sc008_convergence_query_excludes_embedding_column() -> None:
    """The convergence subquery is a column-list, not SELECT *.

    This is the structural enforcement of SC-008: an explicit column list
    means a future schema addition (e.g. `embedding_v2`) can't slip into
    the export by default. Any change to add a SELECT * here would have
    to delete this assertion.
    """
    sql = _LOG_QUERIES["convergence"]
    assert "SELECT *" not in sql.upper()
    assert "embedding" not in sql.lower()
    # Confirms the chosen columns are scalars only.
    expected_columns = (
        "turn_number",
        "session_id",
        "similarity_score",
        "divergence_prompted",
        "escalated_to_human",
    )
    for col in expected_columns:
        assert col in sql


def test_sc008_jsonify_bytes_become_placeholder_not_raw() -> None:
    """`_jsonify` coerces any stray bytes column to a ``<N bytes>`` placeholder.

    Belt-and-suspenders: even if a future query accidentally pulls a
    bytes-typed column, the serializer scrubs it before JSON encoding.
    """
    out = _jsonify(b"\x00\x01\x02\x03 raw embedding bytes")
    assert isinstance(out, str)
    assert out.startswith("<")
    assert out.endswith(" bytes>")
    # The raw bytes content must not appear in the placeholder.
    assert "raw embedding" not in out


def test_sc008_jsonify_recurses_into_nested_bytes() -> None:
    """Bytes inside dicts and lists are scrubbed too."""
    payload = {
        "outer": [
            {"inner_bytes": b"secret-bytes-here", "name": "row-1"},
            {"inner_bytes": b"another-secret", "name": "row-2"},
        ],
    }
    out = _jsonify(payload)
    serialized = repr(out)
    assert "secret-bytes-here" not in serialized
    assert "another-secret" not in serialized
    assert serialized.count("bytes>") == 2


# ---------------------------------------------------------------------------
# FR-9 strip-list contents pinned
# ---------------------------------------------------------------------------


def test_fr9_strip_list_contains_canonical_sensitive_fields() -> None:
    """Every documented sensitive field is in `_SENSITIVE_FIELDS`."""
    required = {
        "api_key_encrypted",
        "auth_token_hash",
        "auth_token_lookup",
        "bound_ip",
    }
    assert required.issubset(_SENSITIVE_FIELDS)


def test_fr9_scrub_drops_every_sensitive_field() -> None:
    """`_scrub` removes every key in `_SENSITIVE_FIELDS` from a record."""
    record = {
        "id": "p-1",
        "display_name": "Alice",
        "api_key_encrypted": b"opaque",
        "auth_token_hash": "bcrypt-hash",
        "auth_token_lookup": "hmac-lookup",
        "bound_ip": "10.0.0.1",
        "provider": "anthropic",
    }
    scrubbed = _scrub(record)
    for k in _SENSITIVE_FIELDS:
        assert k not in scrubbed
    assert scrubbed["id"] == "p-1"
    assert scrubbed["display_name"] == "Alice"
    assert scrubbed["provider"] == "anthropic"


# ---------------------------------------------------------------------------
# FR-6 / SC-007: read-only — only the FR-8 audit row writes
# ---------------------------------------------------------------------------


def test_fr6_export_handler_has_one_write_call_to_audit_log() -> None:
    """Inspecting the source: exactly one write call, to admin_audit_log.

    Read-only is a structural property of the handler. The only INSERT
    is the FR-8 forensic audit row. Any code change that adds another
    write must amend this test (the audit-plan tracker catches the drift).
    """
    src = inspect.getsource(debug_module)
    # log_admin_action is the FR-8 audit-row writer; everything else is reads.
    assert src.count("log_admin_action") == 1
    # Direct DB writes via execute() must not appear in the data-fetch path.
    # _LOG_QUERIES contents are SELECTs only.
    for sql in _LOG_QUERIES.values():
        upper = sql.upper().lstrip()
        assert upper.startswith("SELECT")


def test_fr6_log_queries_are_select_only() -> None:
    """No INSERT / UPDATE / DELETE / TRUNCATE / DROP in the export query set."""
    forbidden_verbs = ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE ", "DROP ", "ALTER ")
    for name, sql in _LOG_QUERIES.items():
        upper = sql.upper()
        for verb in forbidden_verbs:
            assert verb not in upper, f"{name} query contains forbidden verb {verb!r}"


# ---------------------------------------------------------------------------
# FR-5 empty-collections contract — exercised via direct serializer call
# ---------------------------------------------------------------------------


def test_fr5_empty_dict_serializes_to_empty_dict() -> None:
    """Empty dicts pass through _jsonify unchanged (not None, not omitted)."""
    assert _jsonify({}) == {}


def test_fr5_empty_list_serializes_to_empty_list() -> None:
    """Empty lists pass through _jsonify unchanged."""
    assert _jsonify([]) == []


# ---------------------------------------------------------------------------
# Defensive: response shape stability — _CONFIG_KEYS is a tuple, not a set
# ---------------------------------------------------------------------------


def test_config_keys_is_an_ordered_tuple() -> None:
    """`_CONFIG_KEYS` must be ordered so snapshot key-order is reproducible.

    Operators diff exports across deploys. Snapshot key-order being
    deterministic (tuple-driven, not set-driven) is the contract that
    makes those diffs readable.
    """
    assert isinstance(_CONFIG_KEYS, tuple)


def test_secret_name_pattern_anchors_at_end() -> None:
    """The pattern must be suffix-anchored — middle-of-name matches are noise."""
    # `KEY` mid-name shouldn't trigger; `_KEY` at end should.
    assert _SECRET_NAME_PATTERN.search("SACP_KEYBOARD_LAYOUT") is None
    assert _SECRET_NAME_PATTERN.search("SACP_LAYOUT_KEY") is not None
    # Confirm the regex source uses an end-anchor.
    assert _SECRET_NAME_PATTERN.pattern.rstrip().endswith("$")


# ---------------------------------------------------------------------------
# Audit-trail: FR-8 admin_audit_log row is written with the canonical action
# ---------------------------------------------------------------------------


def test_fr8_audit_action_string_is_debug_export() -> None:
    """The canonical FR-8 audit `action` value is ``debug_export``."""
    src = inspect.getsource(debug_module)
    # Locate the exact admin-audit call payload.
    match = re.search(r'action="([^"]+)"', src)
    assert match is not None
    assert match.group(1) == "debug_export"
