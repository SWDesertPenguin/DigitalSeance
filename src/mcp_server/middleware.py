"""Auth middleware — bearer token validation as FastAPI dependency."""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.service import AuthService
from src.mcp_server.rate_limiter import RateLimiter
from src.models.participant import Participant
from src.repositories.errors import (
    AuthRequiredError,
    IPBindingMismatchError,
    TokenExpiredError,
    TokenInvalidError,
)

_bearer_scheme = HTTPBearer()


async def get_auth_service(request: Request) -> AuthService:
    """Extract AuthService from app state."""
    return request.app.state.auth_service


def get_rate_limiter(request: Request) -> RateLimiter:
    """Extract RateLimiter from app state."""
    return request.app.state.rate_limiter


async def get_current_participant(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> Participant:
    """Validate bearer token and return authenticated participant."""
    client_ip = _get_client_ip(request)
    try:
        participant = await auth_service.authenticate(
            credentials.credentials,
            client_ip,
        )
    except (TokenInvalidError, TokenExpiredError, AuthRequiredError) as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e
    except IPBindingMismatchError as e:
        raise HTTPException(status_code=403, detail="IP binding mismatch") from e
    # Rate limit check after successful auth
    limiter = get_rate_limiter(request)
    limiter.check(participant.id)
    return participant


def _get_client_ip(request: Request) -> str:
    """Extract client IP, optionally honoring X-Forwarded-For.

    Trusting X-Forwarded-For unconditionally lets any direct attacker
    bypass IP binding by claiming the legitimate user's IP in the
    header. The IP-binding feature in AuthService exists specifically
    to defend against bearer-token theft on shared networks; an
    attacker-controllable header trivially nullifies that defense.

    By default we use ``request.client.host``. Operators who run SACP
    behind a reverse proxy that overwrites XFF can opt in by setting
    ``SACP_TRUST_PROXY=1``; we then take the *rightmost* XFF value
    (the proxy's view of the immediate client) since proxies append
    to the header rather than prepend.
    """
    direct = request.client.host if request.client else "unknown"
    if os.environ.get("SACP_TRUST_PROXY", "0") != "1":
        return direct
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return direct
    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    return parts[-1] if parts else direct
