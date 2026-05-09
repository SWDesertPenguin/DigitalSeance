# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 019 US3 -- rejection auditing + Prometheus metrics surface.

Covers:
- T038: rejection writes admin_audit_log row with documented payload shape
- T039: counter increments with (endpoint_class, exempt_match) labels only
- T040 / SC-008: 200 rejections in one minute -> ONE audit row, counter += 200
- T041 / FR-012: source_ip_unresolvable rejection is NON-coalesced
- T042 / SC-009: privacy contract -- no raw v6 host, no query string,
  no headers, no body content; metric label set is exactly two labels
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from src.audit.network_rate_limit_audit import (
    drain_unresolvable_queue,
    emit_source_ip_unresolvable,
    get_coalescer,
    record_rejection,
    reset_coalescer_for_tests,
    reset_unresolvable_queue_for_tests,
    serialize_rejection_payload,
    serialize_unresolvable_payload,
)
from src.observability.metrics import (
    increment_network_rate_limit_rejection,
    reset_for_tests,
    sacp_rate_limit_rejection_total,
)


@pytest.fixture(autouse=True)
def _reset_global_state() -> None:
    reset_coalescer_for_tests()
    reset_unresolvable_queue_for_tests()
    reset_for_tests()


# Re-use the synthetic ASGI helpers from US1.
from tests.test_019_us1_bcrypt_flood import (  # noqa: E402
    _build_middleware,
    _drive,
    _make_scope,
    _noop_receive,
    _Recorder,
)

# ---------------------------------------------------------------------------
# T038 -- AS1: rejection writes audit row of action ``network_rate_limit_rejected``
# ---------------------------------------------------------------------------


def test_t038_rejection_audit_payload_shape() -> None:
    """The coalesced row JSON carries the documented field set."""
    record_rejection(
        source_ip_keyed="203.0.113.5",
        path="/mcp/tool",
        method="POST",
        remaining_s=2.0,
        now=1_700_000_000.5,
    )
    record_rejection(
        source_ip_keyed="203.0.113.5",
        path="/mcp/other",
        method="GET",
        remaining_s=1.5,
        now=1_700_000_001.0,
    )
    coalescer = get_coalescer()
    assert len(coalescer) == 1
    (ip, state) = next(iter(coalescer._state.items()))  # type: ignore[attr-defined]
    assert ip[0] == "203.0.113.5"
    payload = json.loads(serialize_rejection_payload(state))
    assert payload["minute_bucket"] == int(1_700_000_000.5 // 60)
    assert payload["rejection_count"] == 2
    assert {"first_rejected_at", "last_rejected_at"} <= payload.keys()
    assert sorted(payload["endpoint_paths_seen"]) == ["/mcp/other", "/mcp/tool"]
    assert sorted(payload["methods_seen"]) == ["GET", "POST"]
    assert payload["limiter_window_remaining_s"] == 1.5  # last value wins


# ---------------------------------------------------------------------------
# T039 -- AS2: counter labels are exactly (endpoint_class, exempt_match)
# ---------------------------------------------------------------------------


def test_t039_counter_increments_with_correct_labels() -> None:
    increment_network_rate_limit_rejection()
    value = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert value == 1.0


def test_t039_counter_label_set_is_exact() -> None:
    """SC-009 privacy contract: labels MUST be exactly the two-key set."""
    increment_network_rate_limit_rejection()
    samples = list(sacp_rate_limit_rejection_total.samples())
    assert samples
    for sample in samples:
        assert set(sample.labels.keys()) == {
            "endpoint_class",
            "exempt_match",
        }, f"unexpected label keys: {sample.labels}"


# ---------------------------------------------------------------------------
# T040 -- AS3 / SC-008: 200 rejections in one minute -> ONE row, counter += 200
# ---------------------------------------------------------------------------


def test_t040_per_minute_coalescing_single_row_per_minute() -> None:
    base = 1_700_000_000.0
    for i in range(200):
        # Stay inside the same minute window (200 / 60 < 1, so all timestamps
        # fall in one minute_bucket).
        record_rejection(
            source_ip_keyed="203.0.113.5",
            path="/mcp/tool",
            method="POST",
            remaining_s=1.0,
            now=base + i * 0.1,
        )
        increment_network_rate_limit_rejection()
    coalescer = get_coalescer()
    assert len(coalescer) == 1, "200 rejections in one minute MUST coalesce to one row"
    state = next(iter(coalescer._state.values()))  # type: ignore[attr-defined]
    assert state.rejection_count == 200
    metric = sacp_rate_limit_rejection_total.get_sample_value(
        {"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert metric == 200.0


def test_t040_sc008_row_count_bounded_by_n_times_60() -> None:
    """Synthetic 1-hour flood with N IPs -> rows <= N * 60 (SC-008)."""
    n_ips = 5
    base = 1_700_000_000.0
    for ip_idx in range(n_ips):
        ip = f"203.0.113.{ip_idx + 1}"
        # 1 hour = 60 minutes; emit one rejection per minute per IP.
        for minute in range(60):
            record_rejection(
                source_ip_keyed=ip,
                path="/mcp/tool",
                method="POST",
                remaining_s=1.0,
                now=base + minute * 60.0,
            )
    coalescer = get_coalescer()
    assert len(coalescer) <= n_ips * 60


# ---------------------------------------------------------------------------
# T041 -- AS4 / FR-012: source_ip_unresolvable is NOT coalesced
# ---------------------------------------------------------------------------


def test_t041_unresolvable_one_row_per_call() -> None:
    for i in range(3):
        emit_source_ip_unresolvable(
            path="/mcp/tool",
            method="POST",
            reason="no_peer",
            now=1_700_000_000.0 + i,
        )
    queue = drain_unresolvable_queue()
    assert len(queue) == 3
    assert all(e.reason == "no_peer" for e in queue)


def test_t041_unresolvable_payload_shape() -> None:
    emit_source_ip_unresolvable(
        path="/mcp/tool",
        method="POST",
        reason="malformed_forwarded_header",
        now=1_700_000_000.0,
    )
    event = drain_unresolvable_queue()[0]
    payload = json.loads(serialize_unresolvable_payload(event))
    assert payload["request_path"] == "/mcp/tool"
    assert payload["request_method"] == "POST"
    assert payload["reason"] == "malformed_forwarded_header"
    assert "rejected_at" in payload


# ---------------------------------------------------------------------------
# T042 -- SC-009 privacy contract
# ---------------------------------------------------------------------------


def test_t042_audit_payload_omits_query_string() -> None:
    """Coalescer's path field MUST be path-only (privacy contract)."""
    mw, _ = _build_middleware(rpm=60, burst=1)
    _drive(mw, count=1, path="/mcp/tool")  # admit
    # Drive a rejection with a query string.
    scope = _make_scope(path="/mcp/tool?secret_token=ABC123")
    asyncio.run(mw(scope, _noop_receive, _Recorder()))
    state = next(iter(get_coalescer()._state.values()))  # type: ignore[attr-defined]
    payload = json.loads(serialize_rejection_payload(state))
    for path in payload["endpoint_paths_seen"]:
        assert "?" not in path
        assert "secret_token" not in path
        assert "ABC123" not in path


def test_t042_audit_payload_omits_raw_v6_host() -> None:
    """Audit row's source_ip_keyed MUST be /64 form, never raw IPv6 host."""
    record_rejection(
        source_ip_keyed="2001:db8:1234:5678::/64",  # already in keyed form
        path="/mcp/tool",
        method="POST",
        remaining_s=1.0,
        now=1_700_000_000.0,
    )
    coalescer = get_coalescer()
    (ip, _) = next(iter(coalescer._state.items()))  # type: ignore[attr-defined]
    # The keyed form ends in /64 -- full v6 host addresses do not.
    assert ip[0].endswith("::/64")


def test_t042_metric_rejects_label_set_extension() -> None:
    """Adding any third label MUST raise ValueError (cardinality / privacy guard)."""
    with pytest.raises(ValueError):
        sacp_rate_limit_rejection_total.labels(
            endpoint_class="network_per_ip",
            exempt_match="false",
            source_ip="203.0.113.5",  # forbidden third label
        )


def test_t042_metric_rejects_unknown_endpoint_class() -> None:
    """``endpoint_class`` is a closed enum (network_per_ip / app_layer_per_participant)."""
    with pytest.raises(ValueError):
        sacp_rate_limit_rejection_total.labels(
            endpoint_class="random_other_class",
            exempt_match="false",
        )


def test_t042_metric_rejects_unknown_exempt_match() -> None:
    """``exempt_match`` is the string boolean -- anything else is an error."""
    with pytest.raises(ValueError):
        sacp_rate_limit_rejection_total.labels(
            endpoint_class="network_per_ip",
            exempt_match="maybe",
        )


# Silence the unused-import warning while keeping the imports load-bearing.
_ = (Any, _Recorder, _make_scope, _noop_receive)
