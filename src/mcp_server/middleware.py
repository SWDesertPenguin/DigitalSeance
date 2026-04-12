"""Auth middleware — bearer token validation as FastAPI dependency."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.service import AuthService
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


async def get_current_participant(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> Participant:
    """Validate bearer token and return authenticated participant."""
    client_ip = _get_client_ip(request)
    try:
        return await auth_service.authenticate(
            credentials.credentials,
            client_ip,
        )
    except (TokenInvalidError, TokenExpiredError, AuthRequiredError) as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e
    except IPBindingMismatchError as e:
        raise HTTPException(status_code=403, detail="IP binding mismatch") from e


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
