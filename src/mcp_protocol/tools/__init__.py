# SPDX-License-Identifier: AGPL-3.0-or-later
"""Registry loader. Spec 030 Phase 3, FR-069 + FR-061."""

from __future__ import annotations

import os

from src.mcp_protocol.tools import (
    admin_tools,
    audit_tools,
    debug_tools,
    detection_event_tools,
    participant_tools,
    proposal_tools,
    provider_tools,
    review_gate_tools,
    scratch_tools,
    session_tools,
)
from src.mcp_protocol.tools.registry import RegistryEntry

_CATEGORY_MAP: list[tuple[str, object]] = [
    ("SACP_MCP_TOOL_SESSION_ENABLED", session_tools),
    ("SACP_MCP_TOOL_PARTICIPANT_ENABLED", participant_tools),
    ("SACP_MCP_TOOL_PROPOSAL_ENABLED", proposal_tools),
    ("SACP_MCP_TOOL_REVIEW_GATE_ENABLED", review_gate_tools),
    ("SACP_MCP_TOOL_DEBUG_EXPORT_ENABLED", debug_tools),
    ("SACP_MCP_TOOL_AUDIT_LOG_ENABLED", audit_tools),
    ("SACP_MCP_TOOL_DETECTION_EVENTS_ENABLED", detection_event_tools),
    ("SACP_MCP_TOOL_SCRATCH_ENABLED", scratch_tools),
    ("SACP_MCP_TOOL_PROVIDER_ENABLED", provider_tools),
    ("SACP_MCP_TOOL_ADMIN_ENABLED", admin_tools),
]


def _is_enabled(env_var: str) -> bool:
    return os.environ.get(env_var, "true").lower() != "false"


def _build_registry() -> dict[str, RegistryEntry]:
    reg: dict[str, RegistryEntry] = {}
    for env_var, module in _CATEGORY_MAP:
        if _is_enabled(env_var):
            module.register(reg)  # type: ignore[attr-defined]
    return reg


REGISTRY: dict[str, RegistryEntry] = _build_registry()
