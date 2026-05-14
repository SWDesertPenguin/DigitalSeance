# SPDX-License-Identifier: AGPL-3.0-or-later
"""OAuth 2.1 discovery metadata endpoint. Spec 030 Phase 4 FR-075."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.mcp_protocol.auth.scope_grant import SCOPE_VOCABULARY

oauth_discovery_router = APIRouter(tags=["oauth"])


@oauth_discovery_router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource(request: Request) -> JSONResponse:
    """Return OAuth 2.1 protected resource metadata per MCP spec revision 2025-11-25."""
    base = str(request.base_url).rstrip("/")
    scopes_list = sorted(SCOPE_VOCABULARY)
    body = {
        "resource": f"{base}/mcp",
        "authorization_servers": [f"{base}/authorize"],
        "scopes_supported": scopes_list,
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{base}/docs/oauth-mcp.md",
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "revocation_endpoint": f"{base}/revoke",
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "client_registration_endpoint": f"{base}/oauth/register-cimd",
        "client_id_metadata_documents_supported": True,
    }
    return JSONResponse(
        content=body,
        headers={"Cache-Control": "public, max-age=300"},
    )
