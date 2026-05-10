# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 account-router endpoints (T047 / T048).

Mounts the seven account-management endpoints documented in
``specs/023-user-accounts/contracts/account-endpoints.md``:

US1 (T044-T046, fully implemented):
  - ``POST /tools/account/create``
  - ``POST /tools/account/verify``
  - ``POST /tools/account/login``

US3 (Phase 5; this module returns 501 stubs until T063-T066 land):
  - ``POST /tools/account/email/change``
  - ``POST /tools/account/email/verify``
  - ``POST /tools/account/password/change``
  - ``POST /tools/account/delete``

The router itself is mounted conditionally by ``src/web_ui/app.py``
via :func:`src.accounts.should_mount_account_router` (FR-018 +
research §12). When the master switch is off the router is NEVER
included on the FastAPI app, so every endpoint resolves to 404
through normal route-not-found handling — the master-switch-off
canary (T035) asserts this contract holds.

Cookie semantics on login: the route layer reuses the existing spec
011 cookie format (``COOKIE_NAME`` from :mod:`src.web_ui.auth`) so
the SPA's existing cookie-resolve flow keeps working. The signed
payload carries the opaque sid only — never the bearer, never the
account_id (FR-016 + audit H-02).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field

from src.accounts.rate_limit import RateLimitExceeded
from src.accounts.service import AccountService, AccountServiceError
from src.web_ui.auth import (
    COOKIE_MAX_AGE_SECONDS,
    COOKIE_NAME,
    _make_cookie_value,
    _parse_cookie_value,
    _secure_cookie_flag,
    extract_client_ip,
)
from src.web_ui.session_store import SessionEntry

log = logging.getLogger(__name__)

router = APIRouter(tags=["spec_023_accounts"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class _CreateBody(BaseModel):
    """Request body for ``POST /tools/account/create``."""

    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=4096)


class _VerifyBody(BaseModel):
    """Request body for ``POST /tools/account/verify``."""

    account_id: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=1, max_length=64)


class _LoginBody(BaseModel):
    """Request body for ``POST /tools/account/login``."""

    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=4096)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_account_service(request: Request) -> AccountService:
    """Return the per-app AccountService or raise 503 if not wired.

    The lifespan in ``src/web_ui/app.py`` attaches the service to
    ``app.state.account_service`` when the mount gate passes; tests
    inject their own via the same attribute.
    """
    service = getattr(request.app.state, "account_service", None)
    if not isinstance(service, AccountService):
        raise HTTPException(
            status_code=503,
            detail="Account service not available",
        )
    return service


def _set_session_cookie(response: Response, request: Request, sid: str) -> None:
    """Issue the spec 011 session cookie carrying only the opaque sid."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=_make_cookie_value(sid),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookie_flag(request),
        samesite="strict",
        path="/",
    )


async def _require_account_session(
    request: Request,
    sacp_ui_token: Annotated[str | None, Cookie()] = None,
) -> tuple[SessionEntry, str]:
    """Resolve the cookie sid → ``SessionEntry`` and require account_id.

    Spec 023 FR-016: account-cookie auth shares the spec 011 cookie
    plumbing (signed sid; lookup against ``SessionStore``). The
    additional gate is that ``entry.account_id`` MUST be set — token-
    paste sessions are rejected so the account-only surface stays
    isolated from the legacy participant-token flow.
    """
    if not sacp_ui_token:
        raise HTTPException(401, detail={"error": "not_authenticated"})
    sid = _parse_cookie_value(sacp_ui_token)
    store = request.app.state.session_store
    entry = await store.get(sid)
    if entry is None or entry.account_id is None:
        raise HTTPException(401, detail={"error": "not_authenticated"})
    return entry, sid


def _to_http(exc: AccountServiceError) -> HTTPException:
    """Translate a service-layer error to the documented HTTP shape."""
    detail: dict[str, object] = {"error": exc.error_code}
    headers: dict[str, str] | None = None
    if exc.error_code == "rate_limit_exceeded":
        # The retry-after value lives on the underlying exception's
        # message ("retry_after=N"); we extract a best-effort integer.
        retry_after = "60"
        if exc.__cause__ is not None and isinstance(exc.__cause__, RateLimitExceeded):
            retry_after = str(exc.__cause__.retry_after_seconds)
        headers = {"Retry-After": retry_after}
    return HTTPException(
        status_code=exc.http_status,
        detail=detail,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# US1 endpoints — fully implemented (T044-T046)
# ---------------------------------------------------------------------------


@router.post("/tools/account/create", status_code=status.HTTP_201_CREATED)
async def create_account_endpoint(
    body: _CreateBody,
    request: Request,
) -> dict:
    """Create a fresh account in ``pending_verification`` status (FR-005).

    Returns 201 + ``{account_id, status, verification_email_sent}`` on
    success; 422 / 409 / 429 per the documented error mapping.
    """
    service = _resolve_account_service(request)
    client_ip = extract_client_ip(request)
    try:
        result = await service.create_account(
            email=body.email,
            password=body.password,
            client_ip=client_ip,
        )
    except AccountServiceError as exc:
        raise _to_http(exc) from exc
    return {
        "account_id": result.account_id,
        "status": result.status,
        "verification_email_sent": result.verification_email_sent,
    }


@router.post("/tools/account/verify")
async def verify_account_endpoint(
    body: _VerifyBody,
    request: Request,
) -> dict:
    """Consume a verification code and flip the account to active (FR-006)."""
    service = _resolve_account_service(request)
    try:
        new_status = await service.verify_account(
            account_id=body.account_id,
            code=body.code,
        )
    except AccountServiceError as exc:
        raise _to_http(exc) from exc
    return {
        "account_id": body.account_id,
        "status": new_status,
    }


@router.post("/tools/account/login")
async def login_endpoint(
    body: _LoginBody,
    request: Request,
    response: Response,
) -> dict:
    """Authenticate by email + password; set the session cookie (FR-007)."""
    service = _resolve_account_service(request)
    client_ip = extract_client_ip(request)
    try:
        result = await service.login(
            email=body.email,
            password=body.password,
            client_ip=client_ip,
        )
    except AccountServiceError as exc:
        raise _to_http(exc) from exc
    _set_session_cookie(response, request, result.sid)
    return {
        "account_id": result.account_id,
        "expires_in": COOKIE_MAX_AGE_SECONDS,
    }


# ---------------------------------------------------------------------------
# US2 endpoints — /me/sessions + rebind (T056, T057)
# ---------------------------------------------------------------------------


@router.get("/me/sessions")
async def list_me_sessions_endpoint(
    request: Request,
    sacp_ui_token: Annotated[str | None, Cookie()] = None,
    active_offset: Annotated[int, Query(ge=0)] = 0,
    archived_offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Return the authenticated account's segmented session list (FR-008)."""
    entry, _ = await _require_account_session(request, sacp_ui_token)
    service = _resolve_account_service(request)
    try:
        return await service.list_sessions(
            account_id=entry.account_id,
            active_offset=active_offset,
            archived_offset=archived_offset,
        )
    except AccountServiceError as exc:
        raise _to_http(exc) from exc


@router.post("/me/sessions/{session_id}/rebind")
async def rebind_session_endpoint(
    request: Request,
    session_id: Annotated[str, Path(min_length=1, max_length=128)],
    sacp_ui_token: Annotated[str | None, Cookie()] = None,
) -> dict:
    """Bind the account-cookie sid to a session-scoped participant (FR-016)."""
    entry, sid = await _require_account_session(request, sacp_ui_token)
    service = _resolve_account_service(request)
    try:
        return await service.rebind_to_session(
            account_id=entry.account_id,
            session_id=session_id,
            sid=sid,
        )
    except AccountServiceError as exc:
        raise _to_http(exc) from exc


# ---------------------------------------------------------------------------
# US3 endpoints — 501 stubs until T063-T066 land in Phase 5
# ---------------------------------------------------------------------------


_US3_DETAIL = {"error": "not_implemented"}


@router.post("/tools/account/email/change", status_code=501)
async def email_change_stub_endpoint() -> dict:
    """US3 stub. Implementation lands in T063-T066 / Phase 5."""
    raise HTTPException(status_code=501, detail=_US3_DETAIL)


@router.post("/tools/account/email/verify", status_code=501)
async def email_verify_stub_endpoint() -> dict:
    """US3 stub. Implementation lands in T063-T066 / Phase 5."""
    raise HTTPException(status_code=501, detail=_US3_DETAIL)


@router.post("/tools/account/password/change", status_code=501)
async def password_change_stub_endpoint() -> dict:
    """US3 stub. Implementation lands in T064-T066 / Phase 5."""
    raise HTTPException(status_code=501, detail=_US3_DETAIL)


@router.post("/tools/account/delete", status_code=501)
async def account_delete_stub_endpoint() -> dict:
    """US3 stub. Implementation lands in T065-T066 / Phase 5."""
    raise HTTPException(status_code=501, detail=_US3_DETAIL)
