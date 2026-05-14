# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI router for MCP Streamable HTTP transport. Spec 030 Phase 2, FR-014 -- FR-032."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from src.mcp_protocol.dispatcher import DispatchError, dispatch
from src.mcp_protocol.errors import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    SACP_AUTH_FAILED,
    SACP_E_AUTH,
    SACP_E_INTERNAL,
    SACP_E_SESSION_EXPIRED,
    SACP_STATE_ERROR,
)
from src.mcp_protocol.handshake import _extract_bearer, handle_initialize
from src.mcp_protocol.session import MCPSession, MCPSessionStore, get_session_store

mcp_router = APIRouter(tags=["mcp"])

log = logging.getLogger("sacp.mcp.transport")


def _is_enabled() -> bool:
    return os.environ.get("SACP_MCP_PROTOCOL_ENABLED", "false").lower() == "true"


def _error_response(
    status: int,
    code: int,
    message: str,
    req_id: object,
    data: dict | None = None,
) -> JSONResponse:
    err: dict = {"code": code, "message": message}
    if data:
        err["data"] = data
    return JSONResponse(
        status_code=status,
        content={"jsonrpc": "2.0", "error": err, "id": req_id},
    )


_EXPIRED_DATA = {"sacp_error_code": SACP_E_SESSION_EXPIRED, "reason": "mcp_session_expired"}


def _check_session_age(
    session: MCPSession, session_id_header: str, store: MCPSessionStore, req_id: object
) -> JSONResponse | None:
    """Return an error response if session has exceeded idle or lifetime limits, else None."""
    idle_timeout = int(os.environ.get("SACP_MCP_SESSION_IDLE_TIMEOUT_SECONDS") or "1800")
    max_lifetime = int(os.environ.get("SACP_MCP_SESSION_MAX_LIFETIME_SECONDS") or "86400")
    now = datetime.now(tz=UTC)
    if (now - session.last_activity_at).total_seconds() > idle_timeout:
        store.remove(session_id_header)
        return _error_response(
            404, SACP_STATE_ERROR, "Session expired (idle timeout)", req_id, _EXPIRED_DATA
        )
    if (now - session.created_at).total_seconds() > max_lifetime:
        store.remove(session_id_header)
        return _error_response(
            404, SACP_STATE_ERROR, "Session expired (max lifetime)", req_id, _EXPIRED_DATA
        )
    return None


def _validate_session(
    session_id_header: str, store: MCPSessionStore, req_id: object
) -> MCPSession | JSONResponse:
    """Return MCPSession or an error response if the session is missing/expired."""
    session = store.get(session_id_header)
    if session is None:
        return _error_response(
            404, SACP_STATE_ERROR, "Session not found or expired", req_id, _EXPIRED_DATA
        )
    age_err = _check_session_age(session, session_id_header, store, req_id)
    if age_err is not None:
        return age_err
    store.touch(session_id_header)
    return session


def _build_caller_context(request: Request, params: dict, session_id_header: str | None) -> object:
    """Build CallerContext for a tools/call request."""
    from src.mcp_protocol.caller_context import CallerContext

    store = get_session_store()
    active = store.get(session_id_header) if session_id_header else None
    app_state = getattr(getattr(request, "app", None), "state", None)
    db_pool = getattr(app_state, "pool", None)
    encryption_key = getattr(app_state, "encryption_key", None)
    return CallerContext(
        participant_id=(active.bound_participant_id or "unknown") if active else "unknown",
        session_id=active.bound_sacp_session_id if active else None,
        scopes=frozenset({"any"}),
        is_ai_caller=False,
        mcp_session_id=session_id_header,
        request_id=str(uuid.uuid4()),
        dispatch_started_at=datetime.now(tz=UTC),
        idempotency_key=params.get("_idempotency_key"),
        db_pool=db_pool,
        encryption_key=encryption_key,
    )


async def _run_tool_dispatch(
    ctx: object, tool_name: str, arguments: dict, req_id: object
) -> JSONResponse:
    """Invoke dispatch through routing and return the JSON-RPC response."""
    from src.mcp_protocol.routing import route_or_passthrough

    async def _do() -> dict:
        return await dispatch(ctx, tool_name, arguments)

    try:
        result = await route_or_passthrough(ctx.session_id, _do)
        return JSONResponse(
            status_code=200,
            content={"jsonrpc": "2.0", "result": result, "id": req_id},
        )
    except DispatchError as exc:
        return _error_response(400, exc.code, exc.message, req_id, exc.data)
    except Exception as exc:
        log.warning("unhandled tools/call error: %s", exc, exc_info=True)
        return _error_response(
            500,
            JSONRPC_INTERNAL_ERROR,
            "Internal error",
            req_id,
            {"sacp_error_code": SACP_E_INTERNAL},
        )


async def _handle_tools_call(
    request: Request, body: dict, session_id_header: str | None, req_id: object
) -> JSONResponse:
    """Build CallerContext then dispatch through the tool registry."""
    params = body.get("params") or {}
    ctx = _build_caller_context(request, params, session_id_header)
    return await _run_tool_dispatch(
        ctx, params.get("name", ""), params.get("arguments") or {}, req_id
    )


def _build_tools_list_response(req_id: object) -> JSONResponse:
    """Build the tools/list JSON-RPC response from the live registry."""
    from src.mcp_protocol.dispatcher import get_registry

    tools = [
        {
            "name": e.definition.name,
            "description": e.definition.description,
            "inputSchema": e.definition.paramsSchema,  # noqa: N815
        }
        for e in get_registry().values()
    ]
    return JSONResponse(
        status_code=200,
        content={"jsonrpc": "2.0", "result": {"tools": tools}, "id": req_id},
    )


async def _route_method(
    request: Request, body: dict, method: str, req_id: object, session_id_header: str | None
) -> Response:
    """Route a non-initialize method to the correct handler."""
    # JSON-RPC notifications (no `id`) must be ack'd with 202 No Content per MCP Streamable
    # HTTP. `notifications/initialized` is sent by clients (e.g. mcp-remote) immediately
    # after a successful `initialize` handshake and MUST NOT receive a JSON-RPC envelope.
    if method.startswith("notifications/"):
        return Response(status_code=202)
    if method == "tools/list":
        return _build_tools_list_response(req_id)
    if method == "ping":
        return JSONResponse(status_code=200, content={"jsonrpc": "2.0", "result": {}, "id": req_id})
    if method in ("prompts/list", "resources/list"):
        return _error_response(
            400, JSONRPC_METHOD_NOT_FOUND, f"Method not supported: {method}", req_id
        )
    if method == "tools/call":
        return await _handle_tools_call(request, body, session_id_header, req_id)
    return _error_response(400, JSONRPC_METHOD_NOT_FOUND, f"Unknown method: {method!r}", req_id)


_PARSE_ERROR_BODY = {
    "jsonrpc": "2.0",
    "error": {"code": JSONRPC_PARSE_ERROR, "message": "Parse error"},
    "id": None,
}


async def _parse_body(request: Request) -> dict | JSONResponse:
    """Parse JSON body; return parse-error response on failure."""
    try:
        return await request.json()
    except Exception:
        return JSONResponse(status_code=400, content=_PARSE_ERROR_BODY)


async def _check_auth_and_session(
    request: Request, req_id: object
) -> tuple[str, str | None] | JSONResponse:
    """Validate bearer + optional session header; return (bearer, session_id) or error."""
    bearer = _extract_bearer(request)
    if not bearer:
        return _error_response(
            401, SACP_AUTH_FAILED, "Authentication failed", req_id, {"sacp_error_code": SACP_E_AUTH}
        )
    session_id_header = request.headers.get("mcp-session-id")
    if session_id_header:
        store = get_session_store()
        err = _validate_session(session_id_header, store, req_id)
        if isinstance(err, JSONResponse):
            return err
    return bearer, session_id_header


@mcp_router.post("/mcp")
async def mcp_endpoint(request: Request) -> Response:
    """Single POST endpoint for MCP Streamable HTTP. Returns 404 when switch off."""
    if not _is_enabled():
        return JSONResponse(status_code=404, content={"detail": "MCP protocol not enabled"})
    body_or_err = await _parse_body(request)
    if isinstance(body_or_err, JSONResponse):
        return body_or_err
    body: dict = body_or_err
    req_id = body.get("id")
    method = body.get("method", "")
    if method == "initialize":
        return await handle_initialize(request, body)
    auth_or_err = await _check_auth_and_session(request, req_id)
    if isinstance(auth_or_err, JSONResponse):
        return auth_or_err
    _, session_id_header = auth_or_err
    return await _route_method(request, body, method, req_id, session_id_header)
