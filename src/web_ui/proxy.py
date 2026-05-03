"""Same-origin proxy for MCP tool calls (audit H-02 closure).

The Web UI cookie now resolves to a server-side `SessionEntry` holding
the bearer token; the SPA no longer needs the bearer in JS to call MCP
tools. This router exposes every MCP endpoint under `/api/mcp/<path>`,
forwarding to the configured `SACP_WEB_UI_MCP_ORIGIN` with the bearer
attached server-side.

Why a forwarder rather than mounting the MCP app inline:
  * Run modes already split MCP (port 8750) and Web UI (port 8751)
    into separate uvicorn workers; the SPA spoke to MCP cross-origin
    via the bearer in JS. Keeping the same network shape but moving
    the bearer to the server side preserves operator deploy patterns
    (separate pods, separate logs, separate scaling).
  * Standalone Web UI dev mode points at a remote MCP via env var.

What this router does NOT do:
  * Streaming response bodies — MCP tools return small JSON envelopes.
    If a future tool streams, swap `Response` for `StreamingResponse`
    and use `client.stream(...)`.
  * WebSocket forwarding — the WS endpoint is on the Web UI itself
    (`/ws/{session_id}`), the proxy only handles MCP tool HTTP calls.

Bootstrap allowlist:
  Three MCP endpoints exist precisely because the caller has no token
  yet — the SPA invokes them from the unauthenticated landing screen.
  Gating them behind a session cookie deadlocks the bootstrap (no
  cookie → 401 → user can never create or join a session). Those paths
  forward without an Authorization header; the upstream MCP routes do
  not declare ``Depends(get_current_participant)`` so the absent header
  is correct, not a bypass.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response

from src.web_ui.auth import get_current_session_entry

router = APIRouter(tags=["web_ui_proxy"])

_DEFAULT_MCP_ORIGIN = "http://localhost:8750"
_PROXY_TIMEOUT_S = 30.0

# Pre-auth MCP endpoints. The SPA hits these from the landing screen
# before any session cookie exists; the upstream routes accept them
# without an Authorization header by design.
_UNAUTHENTICATED_PATHS = frozenset(
    {
        "tools/session/create",
        "tools/session/request_join",
        "tools/session/redeem_invite",
    }
)

# Hop-by-hop headers must not be forwarded between client → proxy → upstream
# or upstream → proxy → client. Plus a few that httpx / FastAPI re-derive.
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "host",
    }
)

# Headers we never forward FROM the client to upstream. Authorization is
# added server-side from the session store; cookie carries the Web UI
# session and has no meaning to MCP.
_CLIENT_STRIP = _HOP_BY_HOP | {"authorization", "cookie"}

# Headers we never forward FROM upstream back to the client. set-cookie
# would let MCP clobber the Web UI session cookie; we reject it on the
# return path as defense in depth (MCP shouldn't be setting cookies but
# a misconfigured MCP build mustn't be able to).
_UPSTREAM_STRIP = _HOP_BY_HOP | {"set-cookie"}


def _mcp_origin() -> str:
    """Return the upstream MCP base URL.

    Accepts the same env value as the CSP layer reads. The CSP variant
    can be a space-separated list (multiple allowed origins for
    connect-src); the proxy needs exactly one upstream so it picks the
    first http(s):// entry. Defaults to loopback for run_apps mode.
    """
    raw = os.environ.get("SACP_WEB_UI_MCP_ORIGIN", "").strip()
    if not raw:
        return _DEFAULT_MCP_ORIGIN
    for entry in raw.split():
        if entry.startswith(("http://", "https://")):
            return entry.rstrip("/")
    return _DEFAULT_MCP_ORIGIN


def _filtered_headers(items: Iterable[tuple[str, str]], strip: frozenset[str]) -> dict[str, str]:
    """Drop hop-by-hop + role-specific headers, normalize names to lowercase."""
    out: dict[str, str] = {}
    for name, value in items:
        if name.lower() in strip:
            continue
        out[name] = value
    return out


@router.api_route(
    "/api/mcp/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(
    path: str,
    request: Request,
    sacp_ui_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Forward an MCP tool call upstream with the session-stored bearer.

    For authenticated paths the cookie sid resolves to a SessionEntry
    and the bearer is attached server-side; if the cookie is missing
    or the sid is unknown, the upstream call never fires (401). For
    the bootstrap allowlist (`_UNAUTHENTICATED_PATHS`) the request is
    forwarded with no Authorization header — the upstream routes are
    public by design. On the return path the upstream response is
    repackaged after stripping hop-by-hop and any `Set-Cookie` header.
    """
    upstream_url = f"{_mcp_origin()}/{path}"
    forwarded = _filtered_headers(request.headers.items(), _CLIENT_STRIP)
    if path not in _UNAUTHENTICATED_PATHS:
        entry = await get_current_session_entry(request, sacp_ui_token)
        forwarded["authorization"] = f"Bearer {entry.bearer}"
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT_S) as client:
            upstream = await client.request(
                method=request.method,
                url=upstream_url,
                headers=forwarded,
                params=request.query_params,
                content=body,
            )
    except httpx.RequestError as exc:
        raise HTTPException(502, f"MCP upstream unreachable: {exc.__class__.__name__}") from exc

    response_headers = _filtered_headers(upstream.headers.items(), _UPSTREAM_STRIP)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
