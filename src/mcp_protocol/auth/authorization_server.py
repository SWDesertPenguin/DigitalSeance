# SPDX-License-Identifier: AGPL-3.0-or-later
"""OAuth 2.1 /authorize endpoint. Spec 030 Phase 4 FR-070, FR-072, FR-076, FR-089."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

auth_router = APIRouter(tags=["oauth"])

_INSERT_CODE_SQL = """
    INSERT INTO oauth_authorization_codes
        (code_hash, client_id, participant_id, redirect_uri,
         code_challenge, code_challenge_method, scope,
         issued_at, expires_at)
    VALUES ($1, $2, $3, $4, $5, 'S256', $6, $7, $8)
"""

_LOOKUP_CLIENT_SQL = """
    SELECT client_id, redirect_uris, allowed_scopes, registration_status
    FROM oauth_clients WHERE client_id = $1
"""

_LOOKUP_PARTICIPANT_SQL = """
    SELECT id, provider, status FROM participants WHERE id = $1
"""

_INSERT_AUDIT_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action, target_id, previous_value, new_value)
    VALUES ($1, $2, 'oauth_authorize', $3, NULL, $4)
"""

_INSERT_SECURITY_EVENT_SQL = """
    INSERT INTO security_events
        (session_id, participant_id, event_type, severity, details, timestamp)
    VALUES ($1, $2, $3, $4, $5, $6)
"""

_UPDATE_PKCE_FAIL_SQL = """
    UPDATE oauth_clients
    SET cimd_content = jsonb_set(
        cimd_content,
        '{_pkce_fail_count}',
        COALESCE((cimd_content->>'_pkce_fail_count')::int + 1, 1)::text::jsonb
    )
    WHERE client_id = $1
"""

_GET_PKCE_FAIL_SQL = """
    SELECT (cimd_content->>'_pkce_fail_count')::int AS fail_count
    FROM oauth_clients WHERE client_id = $1
"""


def _auth_code_ttl() -> int:
    val = os.environ.get("SACP_OAUTH_AUTH_CODE_TTL_SECONDS", "60")
    try:
        return max(10, min(600, int(val)))
    except (ValueError, TypeError):
        return 60


def _pkce_threshold() -> int:
    val = os.environ.get("SACP_OAUTH_FAILED_PKCE_THRESHOLD", "10")
    try:
        return max(1, min(1000, int(val)))
    except (ValueError, TypeError):
        return 10


def _redirect_error(
    redirect_uri: str, error: str, description: str, state: str
) -> RedirectResponse:
    params = {"error": error, "error_description": description, "state": state}
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(
        url=redirect_uri + sep + urlencode(params),
        status_code=302,
    )


def _plain_error(status: int, error: str, description: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": error, "error_description": description},
    )


@auth_router.get("/authorize", response_model=None)
async def authorize(request: Request) -> RedirectResponse | JSONResponse:
    """OAuth 2.1 authorization endpoint per RFC 6749 + RFC 7636."""
    p = request.query_params
    response_type = p.get("response_type", "")
    client_id = p.get("client_id", "")
    redirect_uri = p.get("redirect_uri", "")
    scope_str = p.get("scope", "")
    state = p.get("state", "")
    code_challenge = p.get("code_challenge", "")
    code_challenge_method = p.get("code_challenge_method", "")
    subject = p.get("subject", "")

    if not redirect_uri:
        return _plain_error(400, "invalid_request", "redirect_uri is required")

    parsed_uri = urlparse(redirect_uri)
    if not parsed_uri.scheme:
        return _plain_error(400, "invalid_request", "redirect_uri must be an absolute URI")

    if not client_id:
        return _plain_error(400, "invalid_request", "client_id is required")

    pool = getattr(getattr(request, "app", None), "state", None)
    pool = getattr(pool, "pool", None) if pool else None
    if pool is None:
        return _plain_error(500, "server_error", "database unavailable")

    async with pool.acquire() as conn:
        client_row = await conn.fetchrow(_LOOKUP_CLIENT_SQL, client_id)

    if client_row is None or client_row["registration_status"] == "revoked":
        return _plain_error(400, "unauthorized_client", "client_id not registered or revoked")

    if redirect_uri not in (client_row["redirect_uris"] or []):
        return _plain_error(400, "invalid_request", "redirect_uri not registered for this client")

    if not state:
        return _redirect_error(redirect_uri, "invalid_request", "state is required", "")

    if response_type != "code":
        return _redirect_error(
            redirect_uri, "unsupported_response_type", "only code is supported", state
        )

    if code_challenge_method != "S256":
        async with pool.acquire() as conn:
            await conn.execute(_UPDATE_PKCE_FAIL_SQL, client_id)
        return _redirect_error(
            redirect_uri, "unsupported_challenge_method", "only S256 is accepted", state
        )

    if not code_challenge:
        return _redirect_error(redirect_uri, "invalid_request", "code_challenge is required", state)

    if not subject:
        return _redirect_error(redirect_uri, "invalid_request", "subject is required", state)

    async with pool.acquire() as conn:
        participant_row = await conn.fetchrow(_LOOKUP_PARTICIPANT_SQL, subject)

    if participant_row is None:
        return _redirect_error(redirect_uri, "invalid_request", "subject not found", state)

    _human_like = ("human", "facilitator", "sponsor", "pending")
    if participant_row["provider"] == "ai" or participant_row["provider"] not in _human_like:
        async with pool.acquire() as conn:
            await conn.execute(
                _INSERT_SECURITY_EVENT_SQL,
                "oauth",
                subject,
                "oauth_ai_participant_exclusion",
                "medium",
                f"AI participant {subject!r} attempted OAuth flow",
                datetime.now(tz=UTC),
            )
        return _redirect_error(
            redirect_uri, "access_denied", "AI participants may not use OAuth", state
        )

    requested_scopes = set(scope_str.split()) if scope_str else set()
    allowed = set(client_row["allowed_scopes"] or [])
    if requested_scopes and not requested_scopes.issubset(allowed):
        return _redirect_error(
            redirect_uri, "invalid_scope", "requested scope not in client allowed_scopes", state
        )

    granted_scopes = list(requested_scopes & allowed) if requested_scopes else list(allowed)

    threshold = _pkce_threshold()
    async with pool.acquire() as conn:
        fail_row = await conn.fetchrow(_GET_PKCE_FAIL_SQL, client_id)
    fail_count = (fail_row["fail_count"] or 0) if fail_row else 0
    if fail_count >= threshold:
        return _redirect_error(
            redirect_uri, "access_denied", "client temporarily blocked due to PKCE failures", state
        )

    code_cleartext = secrets.token_urlsafe(32)
    code_hash = hashlib.sha256(code_cleartext.encode("ascii")).hexdigest()
    now = datetime.now(tz=UTC)
    expires = now + timedelta(seconds=_auth_code_ttl())

    async with pool.acquire() as conn:
        await conn.execute(
            _INSERT_CODE_SQL,
            code_hash,
            client_id,
            subject,
            redirect_uri,
            code_challenge,
            granted_scopes,
            now,
            expires,
        )
        await conn.execute(
            _INSERT_AUDIT_SQL,
            "oauth",
            subject,
            client_id,
            str({"granted_scope": granted_scopes, "client_id": client_id}),
        )

    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(
        url=redirect_uri + sep + urlencode({"code": code_cleartext, "state": state}),
        status_code=302,
    )
