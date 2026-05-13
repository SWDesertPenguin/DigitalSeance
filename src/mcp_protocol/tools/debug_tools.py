# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP debug_export tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "debug_export"
_COMMON_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")


def _defn(name: str, description: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        paramsSchema={},
        returnSchema={},
        errorContract=_COMMON_ERRORS,
        scopeRequirement="facilitator",
        aiAccessible=False,
        idempotencySupported=False,
        paginationSupported=True,
        v14BudgetMs=5000,
        category=_CAT,
    )


async def _dispatch_debug_export_session(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


async def _dispatch_debug_export_participant_view(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


def register(registry: dict) -> None:
    registry["debug.export_session"] = RegistryEntry(
        definition=_defn("debug.export_session", "Export full session diagnostic dump"),
        dispatch=_dispatch_debug_export_session,
    )
    registry["debug.export_participant_view"] = RegistryEntry(
        definition=_defn(
            "debug.export_participant_view", "Export participant-scoped diagnostic view"
        ),
        dispatch=_dispatch_debug_export_participant_view,
    )
