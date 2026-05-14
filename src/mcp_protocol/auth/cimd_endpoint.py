# SPDX-License-Identifier: AGPL-3.0-or-later
"""CIMD client registration endpoint. Spec 030 Phase 4 FR-073, FR-088."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.mcp_protocol.auth.client_registration import (
    _allowed_hosts_from_env,
    fetch_and_validate_cimd,
    register_client,
)

cimd_router = APIRouter(tags=["oauth"])
_log = logging.getLogger(__name__)


class _CIMDRequest(BaseModel):
    cimd_url: str


@cimd_router.post("/oauth/register-cimd")
async def register_cimd(request: Request, body: _CIMDRequest) -> JSONResponse:
    """Accept a CIMD URL, fetch + validate, register the client."""
    mode = os.environ.get("SACP_OAUTH_CLIENT_REGISTRATION_MODE", "allowlist")

    if mode == "closed":
        return JSONResponse(
            status_code=403,
            content={"error": "registration_closed", "error_description": "registration disabled"},
        )

    allowed_hosts = _allowed_hosts_from_env()
    if mode == "open":
        allowed_hosts = []

    pool = getattr(getattr(request, "app", None), "state", None)
    pool = getattr(pool, "pool", None) if pool else None
    if pool is None:
        return JSONResponse(
            status_code=500,
            content={"error": "server_error", "error_description": "database unavailable"},
        )

    try:
        cimd_content = await fetch_and_validate_cimd(body.cimd_url, allowed_hosts)
    except ValueError:
        # Full validator detail is logged server-side; the response carries a
        # fixed-form description so internal hostnames, resolver state, and
        # exception types never reach the caller.
        _log.warning("CIMD registration rejected", exc_info=True)
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "error_description": "CIMD URL rejected by validation",
            },
        )

    async with pool.acquire() as conn:
        client_id = await register_client(conn, body.cimd_url, cimd_content)

    return JSONResponse(status_code=201, content={"client_id": client_id})
