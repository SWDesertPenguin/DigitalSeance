# SPDX-License-Identifier: AGPL-3.0-or-later

"""Observability surfaces -- Prometheus-shaped counters and helpers.

Spec 019 contributes the ``sacp_rate_limit_rejection_total`` counter
extension (labels ``endpoint_class``, ``exempt_match``). When spec 016
ships its full prometheus_client integration this module can adopt the
real client without changing call sites -- current usage is a thin
in-process counter facade, no third-party dependency (V11).

Cross-refs:
- specs/019-network-rate-limiting/contracts/metrics.md
"""
