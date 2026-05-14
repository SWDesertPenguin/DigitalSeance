# SPDX-License-Identifier: AGPL-3.0-or-later
"""OAuth 2.1 /revoke endpoint per RFC 7009. Spec 030 Phase 4 FR-074, FR-085, FR-092."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, Response

from src.mcp_protocol.auth import token_cache, token_family

revocation_router = APIRouter(tags=["oauth"])

_LOOKUP_REFRESH_SQL = """
    SELECT token_hash, family_id, participant_id, client_id
    FROM oauth_refresh_tokens WHERE token_hash = $1
"""

_REVOKE_REFRESH_SQL = """
    UPDATE oauth_refresh_tokens SET revoked_at = $2 WHERE token_hash = $1
"""

_LOOKUP_ACCESS_SQL = """
    SELECT jti, participant_id, client_id FROM oauth_access_tokens WHERE jti = $1
"""

_REVOKE_ACCESS_SQL = """
    UPDATE oauth_access_tokens SET revoked_at = $2 WHERE jti = $1
"""

_INSERT_AUDIT_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action, target_id, previous_value, new_value)
    VALUES ($1, $2, 'token_revoked', $3, NULL, $4)
"""

_LOOKUP_CLIENT_SQL = """
    SELECT client_id, registration_status FROM oauth_clients WHERE client_id = $1
"""


@revocation_router.post("/revoke")
async def revoke(
    request: Request,
    token: str = Form(...),
    token_type_hint: str = Form(default=""),
    client_id: str = Form(default=""),
) -> Response:
    """RFC 7009 token revocation endpoint. Always returns HTTP 200."""
    pool = getattr(getattr(request, "app", None), "state", None)
    pool = getattr(pool, "pool", None) if pool else None
    if pool is None:
        return Response(status_code=200)

    now = datetime.now(tz=UTC)
    participant_id = "unknown"
    _tok_prefix = token[:16].encode("ascii", errors="replace")
    token_hash_for_audit = hashlib.sha256(_tok_prefix).hexdigest()[:16]

    async with pool.acquire() as conn:
        if client_id:
            client_row = await conn.fetchrow(_LOOKUP_CLIENT_SQL, client_id)
            if client_row is None or client_row["registration_status"] == "revoked":
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_client", "error_description": "client_id unknown"},
                )

        refresh_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        row = await conn.fetchrow(_LOOKUP_REFRESH_SQL, refresh_hash)
        if row is not None:
            participant_id = row["participant_id"]
            await token_family.revoke_family(
                conn,
                row["family_id"],
                reason="explicit token revocation",
                participant_id=participant_id,
            )
            await conn.execute(
                _INSERT_AUDIT_SQL,
                "oauth",
                participant_id,
                client_id or "unknown",
                str({"type": "refresh_token", "hash_prefix": token_hash_for_audit}),
            )
            return Response(status_code=200)

        try:
            import jwt as _jwt

            payload = _jwt.decode(token, options={"verify_signature": False})
            jti = payload.get("jti", "")
            participant_id = payload.get("sub", "unknown")
        except Exception:
            return Response(status_code=200)

        if jti:
            at_row = await conn.fetchrow(_LOOKUP_ACCESS_SQL, jti)
            if at_row is not None:
                await conn.execute(_REVOKE_ACCESS_SQL, jti, now)
                token_cache.mark_revoked(jti)
                await conn.execute(
                    _INSERT_AUDIT_SQL,
                    "oauth",
                    participant_id,
                    client_id or "unknown",
                    str({"type": "access_token", "jti": jti}),
                )

    return Response(status_code=200)
