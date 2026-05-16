# SPDX-License-Identifier: AGPL-3.0-or-later
"""initialize method handler. Spec 030 Phase 2, FR-014 + FR-015 + FR-020 + FR-022."""

from __future__ import annotations

import hashlib

from fastapi import Request
from fastapi.responses import JSONResponse

from src.mcp_protocol.errors import (
    JSONRPC_INVALID_PARAMS,
    SACP_AUTH_FAILED,
    SACP_STATE_ERROR,
)
from src.mcp_protocol.session import CapacityError, MCPSession, get_session_store

SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = ("2025-03-26", "2025-06-18", "2025-11-25")
PREFERRED_PROTOCOL_VERSION: str = SUPPORTED_PROTOCOL_VERSIONS[-1]
_RETRY_AFTER_SECONDS = 30


def _error_body(
    code: int, message: str, req_id: str | int | None, data: dict | None = None
) -> dict:
    err: dict = {"code": code, "message": message}
    if data:
        err["data"] = data
    return {"jsonrpc": "2.0", "error": err, "id": req_id}


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    return token if token else None


def _check_bearer(request: Request, req_id: object) -> str | JSONResponse:
    bearer = _extract_bearer(request)
    if not bearer:
        return JSONResponse(
            status_code=401,
            content=_error_body(SACP_AUTH_FAILED, "Authentication failed", req_id),
        )
    return bearer


def _negotiate_protocol_version(params: dict, req_id: object) -> str | JSONResponse:
    """Pick the version to use for this session.

    Per MCP lifecycle spec: if the client's requested version is one we support,
    echo it back. If not (or omitted), return our preferred version and let the
    client decide whether to proceed. Only error on a structurally invalid value.
    """
    protocol_version = params.get("protocolVersion")
    if protocol_version is None:
        return PREFERRED_PROTOCOL_VERSION
    if not isinstance(protocol_version, str) or not protocol_version:
        return JSONResponse(
            status_code=400,
            content=_error_body(
                JSONRPC_INVALID_PARAMS,
                "protocolVersion must be a non-empty string",
                req_id,
                {"requested": protocol_version, "supported": list(SUPPORTED_PROTOCOL_VERSIONS)},
            ),
        )
    if protocol_version in SUPPORTED_PROTOCOL_VERSIONS:
        return protocol_version
    return PREFERRED_PROTOCOL_VERSION


def _capability_result(negotiated_version: str) -> dict:
    return {
        "protocolVersion": negotiated_version,
        "capabilities": {
            "tools": {"listChanged": False},
            "logging": {},
        },
        "serverInfo": {"name": "SACP", "version": "0.1.0"},
    }


def _create_session(
    bearer: str, negotiated_version: str, req_id: object
) -> MCPSession | JSONResponse:
    """Create a new MCPSession or return a 503 JSONResponse when at capacity."""
    token_hash = hashlib.sha256(bearer.encode()).hexdigest()
    store = get_session_store()
    try:
        return store.create(
            bearer_token_hash=token_hash,
            negotiated_protocol_version=negotiated_version,
        )
    except CapacityError:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
            content=_error_body(SACP_STATE_ERROR, "Capacity reached", req_id),
        )


async def handle_initialize(request: Request, body: dict) -> JSONResponse:
    """Handle the MCP initialize method."""
    req_id = body.get("id")
    params = body.get("params") or {}
    bearer_or_resp = _check_bearer(request, req_id)
    if isinstance(bearer_or_resp, JSONResponse):
        return bearer_or_resp
    version_or_resp = _negotiate_protocol_version(params, req_id)
    if isinstance(version_or_resp, JSONResponse):
        return version_or_resp
    session_or_resp = _create_session(bearer_or_resp, version_or_resp, req_id)
    if isinstance(session_or_resp, JSONResponse):
        return session_or_resp
    return JSONResponse(
        status_code=200,
        headers={"Mcp-Session-Id": session_or_resp.mcp_session_id},
        content={
            "jsonrpc": "2.0",
            "result": _capability_result(version_or_resp),
            "id": req_id,
        },
    )
