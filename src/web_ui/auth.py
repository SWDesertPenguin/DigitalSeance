"""Cookie-based auth for the Web UI.

The UI never stores bearer tokens in JS-accessible storage. On login
the server validates the token via Phase 1's AuthService, then issues
an HttpOnly + Secure + SameSite=Strict cookie bound to
(participant_id, session_id, expiry). Subsequent requests read the
cookie, look up the participant, and enforce the CSRF header
``X-SACP-Request: 1`` on every mutation.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Annotated

import itsdangerous
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.models.participant import Participant
from src.repositories.errors import (
    AuthRequiredError,
    IPBindingMismatchError,
    TokenExpiredError,
    TokenInvalidError,
)

COOKIE_NAME = "sacp_ui_token"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 8  # 8h session window; refresh on each login


router = APIRouter(tags=["web_ui_auth"])


class _LoginBody(BaseModel):
    """Request body for POST /login."""

    token: str = Field(..., min_length=1, max_length=512)


def _signer() -> itsdangerous.URLSafeTimedSerializer:
    """Cookie signer seeded from the orchestrator encryption key.

    Why: reusing the existing SACP_ENCRYPTION_KEY means there is no new
    secret to manage. The cookie value still doesn't contain the
    participant's bearer token — only their id + session binding.
    """
    secret = os.environ.get("SACP_ENCRYPTION_KEY")
    if not secret:
        raise RuntimeError("SACP_ENCRYPTION_KEY must be set for Web UI cookies")
    return itsdangerous.URLSafeTimedSerializer(secret, salt="sacp-ui-cookie-v1")


def _make_cookie_value(participant_id: str, session_id: str, token: str) -> str:
    """Sign a cookie payload binding the browser to participant+session+bearer.

    Storing the bearer in the signed+HttpOnly+Secure+SameSite=Strict cookie
    lets /me restore the SPA's in-memory token after refresh without
    rotating the persistent bearer. Rotating on /me invalidated the
    user's original token, so after logout they couldn't log back in.
    """
    payload = {
        "pid": participant_id,
        "sid": session_id,
        "tok": token,
        "issued_at": datetime.now(tz=UTC).isoformat(),
    }
    return _signer().dumps(json.dumps(payload))


def _parse_cookie_value(signed: str) -> dict:
    """Verify signature + TTL, return decoded payload, else raise."""
    try:
        raw = _signer().loads(signed, max_age=COOKIE_MAX_AGE_SECONDS)
    except itsdangerous.SignatureExpired as e:
        raise HTTPException(401, "Session cookie expired") from e
    except itsdangerous.BadSignature as e:
        raise HTTPException(401, "Invalid session cookie") from e
    return json.loads(raw)


def _secure_cookie_flag() -> bool:
    """Mark cookies Secure unless explicitly overridden for local dev."""
    return os.environ.get("SACP_WEB_UI_INSECURE_COOKIES", "0") != "1"


@router.post("/login")
async def login(
    body: _LoginBody,
    request: Request,
    response: Response,
) -> dict:
    """Exchange a bearer token for a signed HttpOnly session cookie."""
    auth_service = getattr(request.app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(503, "Auth service not available")
    participant = await _authenticate_or_raise(auth_service, body.token, request)
    _set_session_cookie(response, participant.id, participant.session_id, body.token)
    return {
        "participant_id": participant.id,
        "session_id": participant.session_id,
        "role": participant.role,
        "token": body.token,
        "expires_in": COOKIE_MAX_AGE_SECONDS,
    }


async def _authenticate_or_raise(
    auth_service: object,
    token: str,
    request: Request,
) -> Participant:
    """Call AuthService.authenticate and translate errors to HTTPException."""
    client_ip = request.client.host if request.client else "unknown"
    try:
        return await auth_service.authenticate(token, client_ip)  # type: ignore[attr-defined]
    except (AuthRequiredError, TokenInvalidError):
        raise HTTPException(401, "Invalid token") from None
    except TokenExpiredError:
        raise HTTPException(401, "Token expired") from None
    except IPBindingMismatchError as e:
        raise HTTPException(403, str(e)) from None


def _set_session_cookie(
    response: Response,
    participant_id: str,
    session_id: str,
    token: str,
) -> None:
    """Issue the HttpOnly + Secure + SameSite=Strict session cookie."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=_make_cookie_value(participant_id, session_id, token),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookie_flag(),
        samesite="strict",
        path="/",
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the session cookie (same attrs as on issue)."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_secure_cookie_flag(),
        samesite="strict",
    )
    return {"status": "logged_out"}


async def get_current_ui_participant(
    request: Request,
    sacp_ui_token: Annotated[str | None, Cookie()] = None,
) -> Participant:
    """FastAPI dependency: resolve the cookie to a Participant row."""
    if not sacp_ui_token:
        raise HTTPException(401, "Not authenticated")
    payload = _parse_cookie_value(sacp_ui_token)
    participant_repo = getattr(request.app.state, "participant_repo", None)
    if participant_repo is None:
        raise HTTPException(503, "Participant repository not available")
    participant = await participant_repo.get_participant(payload["pid"])
    if participant is None or participant.session_id != payload["sid"]:
        raise HTTPException(401, "Cookie does not match a current participant")
    return participant


UiParticipant = Annotated[Participant, Depends(get_current_ui_participant)]


@router.get("/me")
async def whoami(
    sacp_ui_token: Annotated[str | None, Cookie()] = None,
    participant: Participant = Depends(get_current_ui_participant),
) -> dict:
    """Restore session state on page refresh.

    The HttpOnly cookie carries the bearer so the SPA can re-hydrate
    after F5 without rotating the user's persistent token. Previous
    behavior rotated on every /me which invalidated the user's copy of
    the token — so after logout they could not log back in.
    """
    payload = _parse_cookie_value(sacp_ui_token) if sacp_ui_token else {}
    return {
        "participant_id": participant.id,
        "session_id": participant.session_id,
        "role": participant.role,
        "token": payload.get("tok", ""),
        "expires_in": COOKIE_MAX_AGE_SECONDS,
    }
