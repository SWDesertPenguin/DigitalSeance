# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP provider tool category. Spec 030 Phase 3, FR-069."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "provider"
_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")


async def _dispatch_provider_list(ctx: CallerContext, params: dict) -> dict:
    return {"providers": ["anthropic", "openai", "ollama", "gemini", "groq"]}


async def _dispatch_provider_test_credentials(ctx: CallerContext, params: dict) -> dict:
    return {"error": "SACP_E_NOT_FOUND", "reason": "direct_http_required"}


def _list_defn() -> ToolDefinition:
    return ToolDefinition(
        name="provider.list",
        description="List supported AI providers (no BYOK credential exposure)",
        paramsSchema={},
        returnSchema={},
        errorContract=_ERRORS,
        scopeRequirement="facilitator",
        aiAccessible=False,
        idempotencySupported=False,
        paginationSupported=False,
        v14BudgetMs=200,
        category=_CAT,
    )


def _test_creds_defn() -> ToolDefinition:
    return ToolDefinition(
        name="provider.test_credentials",
        description="Test own BYOK credentials (facilitator MUST NOT test others per FR-084)",
        paramsSchema={},
        returnSchema={},
        errorContract=_ERRORS,
        scopeRequirement="participant",
        aiAccessible=False,
        idempotencySupported=False,
        paginationSupported=False,
        v14BudgetMs=1000,
        category=_CAT,
    )


def register(registry: dict) -> None:
    registry["provider.list"] = RegistryEntry(
        definition=_list_defn(), dispatch=_dispatch_provider_list
    )
    registry["provider.test_credentials"] = RegistryEntry(
        definition=_test_creds_defn(), dispatch=_dispatch_provider_test_credentials
    )
