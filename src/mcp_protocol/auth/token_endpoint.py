# SPDX-License-Identifier: AGPL-3.0-or-later
"""OAuth 2.1 /token endpoint. Spec 030 Phase 4 FR-070, FR-073, FR-078, FR-079, FR-085."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from src.mcp_protocol.auth import jwt_signer, refresh_token_store, token_family

token_router = APIRouter(tags=["oauth"])

_LOOKUP_CODE_SQL = """
    SELECT code_hash, client_id, participant_id, redirect_uri,
           code_challenge, scope, issued_at, expires_at, redeemed_at
    FROM oauth_authorization_codes
    WHERE code_hash = $1
"""

_MARK_CODE_REDEEMED_SQL = """
    UPDATE oauth_authorization_codes SET redeemed_at = $2 WHERE code_hash = $1
"""

_INSERT_AT_SQL = """
    INSERT INTO oauth_access_tokens
        (jti, participant_id, client_id, scope, issued_at, expires_at, family_id, auth_time)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
"""

_INSERT_AUDIT_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action, target_id, previous_value, new_value)
    VALUES ($1, $2, $3, $4, NULL, $5)
"""

_LOOKUP_CLIENT_SQL = """
    SELECT client_id, registration_status FROM oauth_clients WHERE client_id = $1
"""

_LOOKUP_REFRESH_SQL = """
    SELECT token_hash, participant_id, client_id, scope, family_id,
           rotated_at, revoked_at, expires_at
    FROM oauth_refresh_tokens WHERE token_hash = $1
"""


def _access_token_ttl_seconds() -> int:
    val = os.environ.get("SACP_OAUTH_ACCESS_TOKEN_TTL_MINUTES", "60")
    try:
        return max(5, min(1440, int(val))) * 60
    except (ValueError, TypeError):
        return 3600


def _error(status: int, error: str, description: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": error, "error_description": description},
    )


async def _handle_auth_code_grant(
    request: Request,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str,
) -> JSONResponse:
    from src.mcp_protocol.auth.pkce import verify_challenge

    pool = getattr(getattr(request, "app", None), "state", None)
    pool = getattr(pool, "pool", None) if pool else None
    if pool is None:
        return _error(500, "server_error", "database unavailable")

    code_hash = hashlib.sha256(code.encode("ascii")).hexdigest()
    now = datetime.now(tz=UTC)

    async with pool.acquire() as conn:
        client_row = await conn.fetchrow(_LOOKUP_CLIENT_SQL, client_id)
        if client_row is None or client_row["registration_status"] == "revoked":
            return _error(400, "invalid_client", "client_id unknown or revoked")

        code_row = await conn.fetchrow(_LOOKUP_CODE_SQL, code_hash)
        if code_row is None:
            return _error(400, "invalid_grant", "authorization code not found")
        if code_row["client_id"] != client_id:
            return _error(400, "invalid_grant", "client_id mismatch")
        if code_row["redeemed_at"] is not None:
            return _error(400, "invalid_grant", "authorization code already redeemed")
        if code_row["expires_at"] < now:
            return _error(400, "invalid_grant", "authorization code expired")
        if code_row["redirect_uri"] != redirect_uri:
            return _error(400, "invalid_grant", "redirect_uri mismatch")

        if not verify_challenge(code_verifier, code_row["code_challenge"]):
            return _error(400, "invalid_grant", "PKCE verifier does not match challenge")

        participant_id = code_row["participant_id"]
        scope = list(code_row["scope"])
        auth_time_str = now.isoformat()

        root_cleartext, root_hash = await refresh_token_store.issue_refresh_token(
            conn,
            client_id=client_id,
            participant_id=participant_id,
            scope=scope,
            family_id="__placeholder__",
        )

        family_id = await token_family.create_family(
            conn, participant_id, client_id, root_token_hash=root_hash
        )

        await conn.execute(
            "UPDATE oauth_refresh_tokens SET family_id = $1 WHERE token_hash = $2",
            family_id,
            root_hash,
        )

        access_token = jwt_signer.sign_access_token(
            sub=participant_id,
            client_id=client_id,
            scope=scope,
            auth_time=auth_time_str,
        )

        import jwt as _jwt

        payload = _jwt.decode(access_token, options={"verify_signature": False})
        jti = payload["jti"]
        issued_at = datetime.fromtimestamp(payload["iat"], tz=UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)

        await conn.execute(
            _INSERT_AT_SQL,
            jti,
            participant_id,
            client_id,
            scope,
            issued_at,
            expires_at,
            family_id,
            now,
        )

        await conn.execute(_MARK_CODE_REDEEMED_SQL, code_hash, now)

        await conn.execute(
            _INSERT_AUDIT_SQL,
            "oauth",
            participant_id,
            "token_issued",
            client_id,
            str({"scope": scope, "jti": jti}),
        )

    return JSONResponse(
        status_code=200,
        content={
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": _access_token_ttl_seconds(),
            "refresh_token": root_cleartext,
            "scope": " ".join(scope),
        },
    )


async def _handle_refresh_grant(
    request: Request,
    refresh_token: str,
    client_id: str,
) -> JSONResponse:
    pool = getattr(getattr(request, "app", None), "state", None)
    pool = getattr(pool, "pool", None) if pool else None
    if pool is None:
        return _error(500, "server_error", "database unavailable")

    old_hash = hashlib.sha256(refresh_token.encode("ascii")).hexdigest()

    async with pool.acquire() as conn:
        client_row = await conn.fetchrow(_LOOKUP_CLIENT_SQL, client_id)
        if client_row is None or client_row["registration_status"] == "revoked":
            return _error(400, "invalid_client", "client_id unknown or revoked")

        row = await conn.fetchrow(_LOOKUP_REFRESH_SQL, old_hash)
        if row is None:
            return _error(400, "invalid_grant", "refresh token not found")
        if row["client_id"] != client_id:
            return _error(400, "invalid_grant", "client_id mismatch")

        participant_id = row["participant_id"]
        scope = list(row["scope"])

        result = await refresh_token_store.rotate_refresh_token(
            conn, refresh_token, client_id, participant_id, scope
        )
        if result is None:
            return _error(400, "invalid_grant", "refresh token replayed or revoked")

        new_cleartext, new_hash = result

        auth_time_str = datetime.now(tz=UTC).isoformat()
        access_token = jwt_signer.sign_access_token(
            sub=participant_id,
            client_id=client_id,
            scope=scope,
            auth_time=auth_time_str,
        )

        import jwt as _jwt

        payload = _jwt.decode(access_token, options={"verify_signature": False})
        jti = payload["jti"]
        issued_at = datetime.fromtimestamp(payload["iat"], tz=UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        now = datetime.now(tz=UTC)

        await conn.execute(
            _INSERT_AT_SQL,
            jti,
            participant_id,
            client_id,
            scope,
            issued_at,
            expires_at,
            row["family_id"],
            now,
        )

        await conn.execute(
            _INSERT_AUDIT_SQL,
            "oauth",
            participant_id,
            "token_refreshed",
            client_id,
            str({"scope": scope, "jti": jti}),
        )

    return JSONResponse(
        status_code=200,
        content={
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": _access_token_ttl_seconds(),
            "refresh_token": new_cleartext,
            "scope": " ".join(scope),
        },
    )


@token_router.post("/token")
async def token(
    request: Request,
    grant_type: str = Form(...),
    code: str = Form(default=""),
    code_verifier: str = Form(default=""),
    redirect_uri: str = Form(default=""),
    client_id: str = Form(default=""),
    refresh_token: str = Form(default=""),
) -> JSONResponse:
    """OAuth 2.1 token endpoint per RFC 6749."""
    if grant_type == "authorization_code":
        if not code or not code_verifier or not redirect_uri or not client_id:
            return _error(
                400, "invalid_request", "missing required params for authorization_code grant"
            )  # noqa: E501
        return await _handle_auth_code_grant(request, code, code_verifier, redirect_uri, client_id)

    if grant_type == "refresh_token":
        if not refresh_token or not client_id:
            return _error(400, "invalid_request", "missing required params for refresh_token grant")
        return await _handle_refresh_grant(request, refresh_token, client_id)

    return _error(400, "unsupported_grant_type", f"grant_type {grant_type!r} not supported")
