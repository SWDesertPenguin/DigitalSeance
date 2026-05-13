# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 018 — discovery MCP tool endpoints (`tools.list_deferred`, `tools.load_deferred`).

Phase 1 ships the two endpoints as no-op stubs returning a documented
`deferred_loading_disabled` response when `SACP_TOOL_DEFER_ENABLED=false`
(the v1 default). Phase 2 replaces the stub branch with the live
partition/promote/audit path; the handler signatures stay stable
across the transition.

URL paths use snake_case to match the existing SACP-native HTTP
surface (alongside `participant.py`'s `/tools/participant/inject_message`).
The logical tool names (`tools.list_deferred`, `tools.load_deferred`)
match spec 030's `domain.action` snake_case convention so the future
migration onto spec 030's `ToolRegistry` is a renamed-import refactor.

Per FR-014: the two discovery MCP tools MUST be registered (regardless
of master switch state) so the contract is observable on every
deployment.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.mcp_server.middleware import get_current_participant
from src.models.participant import Participant
from src.orchestrator.deferred_tool_index import (
    _deferral_enabled,
    get_deferred_index_for_participant,
)

router = APIRouter(prefix="/tools/participant", tags=["deferred-tools"])

_STUB_RESPONSE = {
    "status": "deferred_loading_disabled",
    "spec": "018",
    "documentation": (
        "Deferred tool loading is disabled in this deployment "
        "(SACP_TOOL_DEFER_ENABLED=false). See spec 018 for activation details."
    ),
}


class _LoadDeferredBody(BaseModel):
    """Request body for tools.load_deferred."""

    name: str = Field(..., min_length=1, max_length=256)


@router.post("/list_deferred_tools")
async def list_deferred_tools(
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """`tools.list_deferred` — return the caller's deferred-tool index.

    Phase 1: returns the documented `deferred_loading_disabled` stub
    when `SACP_TOOL_DEFER_ENABLED=false`. Phase 2: returns the live
    `{deferred, truncated, next_page_token}` payload when enabled.

    Caller scope: participant-callable on their own deferred set only.
    Cross-participant calls are impossible by construction here — the
    `get_current_participant` dependency resolves the caller's identity
    from the request auth, and the index lookup keys on that identity.
    """
    if not _deferral_enabled():
        return dict(_STUB_RESPONSE)
    # Phase 2 lands here — render_index_entries against the live index.
    index = get_deferred_index_for_participant(participant.session_id, participant.id)
    max_tokens = _read_index_max_tokens()
    entries, truncated = index.render_index_entries(max_tokens)
    return {
        "deferred": entries,
        "truncated": truncated,
        "next_page_token": None,
    }


@router.post("/load_deferred_tool")
async def load_deferred_tool(
    body: _LoadDeferredBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """`tools.load_deferred` — promote a deferred tool into the loaded subset.

    Phase 1: returns the documented `deferred_loading_disabled` stub
    when `SACP_TOOL_DEFER_ENABLED=false`. Phase 2: validates the tool
    is in the caller's deferred set, promotes it sticky-within-session,
    emits the `tool_loaded_on_demand` audit row (plus paired
    `tool_re_deferred` row when LRU eviction occurred), invalidates
    the prompt-cache prefix once, and returns the full tool definition.

    Caller scope: participant-callable on their own deferred set only.
    """
    if not _deferral_enabled():
        return dict(_STUB_RESPONSE)
    # Phase 2 lands here — load_on_demand + audit + cache invalidate.
    index = get_deferred_index_for_participant(participant.session_id, participant.id)
    tool = await index.load_on_demand(body.name, all_tools=[])
    if tool is None:
        return {"error": "tool_not_found", "tool_name": body.name}
    return {"tool": tool, "evicted_for_this": None}


def _read_index_max_tokens() -> int:
    """Read SACP_TOOL_DEFER_INDEX_MAX_TOKENS at the default of 256."""
    val = os.environ.get("SACP_TOOL_DEFER_INDEX_MAX_TOKENS", "").strip()
    if not val:
        return 256
    try:
        return int(val)
    except ValueError:
        return 256
