# SPDX-License-Identifier: AGPL-3.0-or-later
"""/.well-known/mcp-server discovery endpoint. Spec 030 Phase 2, FR-024 + SC-023."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.mcp_protocol.handshake import PREFERRED_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS

discovery_router = APIRouter(tags=["mcp-discovery"])

_SERVER_VERSION = "0.1.0"
_SERVER_NAME = "SACP"


@discovery_router.get("/.well-known/mcp-server")
async def mcp_discovery_metadata(request: Request) -> JSONResponse:
    """Return MCP server metadata.

    Responds regardless of SACP_MCP_PROTOCOL_ENABLED. When the switch is off,
    returns {"enabled": false} so clients can discover the switch state
    per FR-024 + SC-023.
    """
    enabled = os.environ.get("SACP_MCP_PROTOCOL_ENABLED", "false").lower() == "true"

    server_block = {"name": _SERVER_NAME, "version": _SERVER_VERSION}

    if not enabled:
        return JSONResponse(
            status_code=200,
            content={"enabled": False, "server": server_block},
        )

    base_url = str(request.base_url).rstrip("/")
    body: dict = {
        "enabled": True,
        "protocol_version": PREFERRED_PROTOCOL_VERSION,
        "supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
        "endpoint_url": f"{base_url}/mcp",
        "auth": {
            "scheme": "bearer",
        },
        "server": server_block,
    }
    return JSONResponse(status_code=200, content=body)
