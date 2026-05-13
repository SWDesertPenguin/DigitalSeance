# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCP scratch tool category. Spec 030 Phase 3, FR-069. Spec 024 not yet implemented."""

from __future__ import annotations

from src.mcp_protocol.caller_context import CallerContext
from src.mcp_protocol.tools.registry import RegistryEntry, ToolDefinition

_CAT = "scratch"
_ERRORS = ("SACP_E_NOT_FOUND", "SACP_E_FORBIDDEN", "SACP_E_INTERNAL", "SACP_E_VALIDATION")
_NOT_IMPL = {"error": "SACP_E_NOT_FOUND", "reason": "spec_024_not_implemented"}


def _defn(
    name: str, desc: str, *, idem: bool = False, page: bool = False, v14: int = 500
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=desc,
        paramsSchema={},
        returnSchema={},
        errorContract=_ERRORS,
        scopeRequirement="facilitator",
        aiAccessible=False,
        idempotencySupported=idem,
        paginationSupported=page,
        v14BudgetMs=v14,
        category=_CAT,
    )


async def _dispatch_scratch_list_notes(ctx: CallerContext, params: dict) -> dict:
    return _NOT_IMPL


async def _dispatch_scratch_create_note(ctx: CallerContext, params: dict) -> dict:
    return _NOT_IMPL


async def _dispatch_scratch_update_note(ctx: CallerContext, params: dict) -> dict:
    return _NOT_IMPL


async def _dispatch_scratch_delete_note(ctx: CallerContext, params: dict) -> dict:
    return _NOT_IMPL


async def _dispatch_scratch_promote_to_transcript(ctx: CallerContext, params: dict) -> dict:
    return _NOT_IMPL


def _register_note_tools(registry: dict) -> None:
    registry["scratch.list_notes"] = RegistryEntry(
        definition=_defn(
            "scratch.list_notes", "List scratch notes (spec 024 stub)", page=True, v14=1000
        ),
        dispatch=_dispatch_scratch_list_notes,
    )
    registry["scratch.create_note"] = RegistryEntry(
        definition=_defn("scratch.create_note", "Create a scratch note (spec 024 stub)", idem=True),
        dispatch=_dispatch_scratch_create_note,
    )
    registry["scratch.update_note"] = RegistryEntry(
        definition=_defn("scratch.update_note", "Update a scratch note (spec 024 stub)", idem=True),
        dispatch=_dispatch_scratch_update_note,
    )


def _register_advanced_tools(registry: dict) -> None:
    registry["scratch.delete_note"] = RegistryEntry(
        definition=_defn("scratch.delete_note", "Delete a scratch note (spec 024 stub)", idem=True),
        dispatch=_dispatch_scratch_delete_note,
    )
    registry["scratch.promote_to_transcript"] = RegistryEntry(
        definition=_defn(
            "scratch.promote_to_transcript",
            "Promote a scratch note to session transcript (spec 024 stub)",
            idem=True,
            v14=1000,
        ),
        dispatch=_dispatch_scratch_promote_to_transcript,
    )


def register(registry: dict) -> None:
    _register_note_tools(registry)
    _register_advanced_tools(registry)
