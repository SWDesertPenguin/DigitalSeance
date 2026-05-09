# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-IP login rate limiter for spec 023 (FR-015, clarify Q10).

Sliding-window deque per IP with a 60-second window and a threshold
sourced from ``SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN``. State is
process-local and intentionally separate from the spec 019 middleware
limiter — the two limiters apply additively per the clarify ruling.

See ``specs/023-user-accounts/research.md`` §5 for the algorithm
choice and additive-composition rationale.
"""
