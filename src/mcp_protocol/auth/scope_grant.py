# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scope vocabulary + grantability matrix. Spec 030 Phase 4 FR-077, FR-084."""

from __future__ import annotations

SCOPE_VOCABULARY: frozenset[str] = frozenset(
    {
        "facilitator",
        "participant",
        "pending",
        "sponsor",
        "tool:session",
        "tool:participant",
        "tool:proposal",
        "tool:review_gate",
        "tool:debug_export",
        "tool:audit_log",
        "tool:detection_events",
        "tool:scratch",
        "tool:provider",
        "tool:admin",
    }
)

_ROLE_SCOPES: frozenset[str] = frozenset(
    {
        "facilitator",
        "participant",
        "pending",
        "sponsor",
    }
)

_TOOL_SCOPES: frozenset[str] = frozenset(
    {
        "tool:session",
        "tool:participant",
        "tool:proposal",
        "tool:review_gate",
        "tool:debug_export",
        "tool:audit_log",
        "tool:detection_events",
        "tool:scratch",
        "tool:provider",
        "tool:admin",
    }
)

_GRANTABLE_BY_KIND: dict[str, frozenset[str]] = {
    "human": SCOPE_VOCABULARY,
    "facilitator": SCOPE_VOCABULARY,
    "participant": frozenset(
        {
            "participant",
            "pending",
            "tool:session",
            "tool:participant",
            "tool:proposal",
            "tool:review_gate",
            "tool:scratch",
        }
    ),
    "pending": frozenset({"pending", "tool:session"}),
    "sponsor": SCOPE_VOCABULARY,
}

_SOVEREIGNTY_EXCLUSIONS: dict[str, str] = {
    "provider.test_credentials": "facilitator",
    "participant.set_budget": "sponsor",
}


def grantable_scopes(participant_kind: str) -> frozenset[str]:
    """Return scopes grantable to this participant kind."""
    return _GRANTABLE_BY_KIND.get(participant_kind, frozenset())


def intersect(requested: set[str], grantable: frozenset[str]) -> frozenset[str]:
    """Return the intersection of requested scopes with the grantable set."""
    return frozenset(requested) & grantable
