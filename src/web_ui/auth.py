# SPDX-License-Identifier: AGPL-3.0-or-later

"""Cookie-based auth for the Web UI.

The UI never stores bearer tokens in JS-accessible storage. On login
the server validates the token via Phase 1's AuthService, then issues
an HttpOnly + Secure + SameSite=Strict cookie carrying an opaque
session id. The bearer + (participant_id, session_id) binding lives
in a process-local server-side store keyed by that sid; the cookie
itself is signed for integrity but contains no participant data and
no bearer.

Audit H-02 / M-08: pre-fix the cookie payload was a base64-readable
JSON blob containing the bearer. Cookie-jar exfiltration (compromised
endpoint, malicious extension, downgraded-link intercept) lifted the
bearer directly. Audit M-02: the signing key reused
``SACP_ENCRYPTION_KEY`` (the at-rest API-key encryption secret), so a
leak of either key gave an attacker both forgery and decryption
capabilities.

Subsequent requests read the cookie, look up the sid, and enforce the
CSRF header ``X-SACP-Request: 1`` on every mutation.
"""

from __future__ import annotations

import contextlib
import logging
import os
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
from src.web_ui.session_store import SessionEntry, SessionStore, get_session_store

COOKIE_NAME = "sacp_ui_token"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 8  # 8h session window; refresh on each login

logger = logging.getLogger(__name__)


router = APIRouter(tags=["web_ui_auth"])


class _LoginBody(BaseModel):
    """Request body for POST /login."""

    token: str = Field(..., min_length=1, max_length=512)


def _signer() -> itsdangerous.URLSafeTimedSerializer:
    """Cookie signer seeded from the dedicated Web UI cookie key.

    Why: SACP_WEB_UI_COOKIE_KEY is independent from SACP_ENCRYPTION_KEY
    so a leak of either secret does not compromise both the at-rest
    API-key encryption and session-cookie integrity. Audit M-02.
    """
    secret = os.environ.get("SACP_WEB_UI_COOKIE_KEY")
    if not secret:
        raise RuntimeError("SACP_WEB_UI_COOKIE_KEY must be set for Web UI cookies")
    return itsdangerous.URLSafeTimedSerializer(secret, salt="sacp-ui-cookie-v2")


def _make_cookie_value(sid: str) -> str:
    """Sign a cookie payload that carries only the opaque sid.

    The payload is a dict (rather than the raw sid string) so future
    additions (e.g. an issued-at marker) don't require a third format
    migration; clients that decode the signature still get a stable
    shape. URLSafeTimedSerializer JSON-encodes the dict before signing.
    """
    return _signer().dumps({"sid": sid})


def _parse_cookie_value(signed: str) -> str:
    """Verify signature + TTL, return the sid, else raise HTTPException."""
    try:
        payload = _signer().loads(signed, max_age=COOKIE_MAX_AGE_SECONDS)
    except itsdangerous.SignatureExpired as e:
        raise HTTPException(401, "Session cookie expired") from e
    except itsdangerous.BadSignature as e:
        raise HTTPException(401, "Invalid session cookie") from e
    sid = payload.get("sid") if isinstance(payload, dict) else None
    if not isinstance(sid, str) or not sid:
        raise HTTPException(401, "Invalid session cookie")
    return sid


def _secure_cookie_flag(request: Request) -> bool:
    """Decide whether the session cookie carries the Secure flag.

    Auto-detect from the request scheme so a LAN/HTTP deployment works
    out of the box: a Secure cookie sent over plain HTTP is stored by
    the browser but never sent back, deadlocking every subsequent
    cookie-authed call (proxy 401, WebSocket 4401, no-op session_set
    silently failing). HTTPS deployments still get Secure cookies
    because the request scheme is `https`.

    Operator overrides:
      * `SACP_WEB_UI_INSECURE_COOKIES=1` — force Secure off regardless
        of scheme. Kept for explicit control and back-compat with
        deployments that already set it.
      * `SACP_TRUST_PROXY=1` — honor `X-Forwarded-Proto` from a fronting
        reverse-proxy doing TLS termination (the inner request looks
        HTTP but the user is on HTTPS). Same env var that governs IP
        binding trust, so the trust decision is co-located.
    """
    if os.environ.get("SACP_WEB_UI_INSECURE_COOKIES") == "1":
        return False
    return _request_scheme(request) == "https"


def _request_scheme(request: Request) -> str:
    """Return `https` or `http` for the inbound request.

    Honors `X-Forwarded-Proto` only when `SACP_TRUST_PROXY=1`; otherwise
    a hostile client could downgrade or upgrade the perceived scheme by
    setting the header themselves. Proxies append to XFF, so the
    rightmost value reflects the proxy's view of its immediate client.
    """
    if os.environ.get("SACP_TRUST_PROXY") == "1":
        forwarded = request.headers.get("x-forwarded-proto", "")
        parts = [p.strip().lower() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.url.scheme


def extract_client_ip(connection: object) -> str:
    """Extract the client IP from a Request or WebSocket consistently.

    Pre-fix `/login` and the `/ws` upgrade both read `connection.client.host`
    directly without honoring `SACP_TRUST_PROXY`. Behind a fronting reverse
    proxy that becomes the proxy's IP, not the user's, while MCP-via-proxy
    correctly extracted the browser IP from XFF — so the bound IP at login
    never matched MCP's view, 403'ing every authenticated tool call. This
    helper unifies the trust decision across all three surfaces.

    Honors `X-Forwarded-For` only when `SACP_TRUST_PROXY=1` (operator
    explicitly says "I'm behind a reverse proxy I control"). Loopback is
    NOT auto-trusted here — `/login` and `/ws` are user-facing surfaces
    never legitimately reached over loopback in production, so an
    on-host attacker who could spoof XFF gains no leverage worth opening
    that door. The MCP middleware's loopback-trust is a separate, narrow
    concession for the in-container Web-UI-proxy hop.
    """
    client = getattr(connection, "client", None)
    direct = client.host if client is not None else "unknown"
    if os.environ.get("SACP_TRUST_PROXY") != "1":
        return direct
    forwarded = connection.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    return parts[-1] if parts else direct


def _resolve_session_store(request: Request) -> SessionStore:
    """Return the per-app SessionStore, falling back to the singleton."""
    store = getattr(request.app.state, "session_store", None)
    if isinstance(store, SessionStore):
        return store
    return get_session_store()


@router.post("/login")
async def login(
    body: _LoginBody,
    request: Request,
    response: Response,
    sacp_ui_token: Annotated[str | None, Cookie()] = None,
) -> dict:
    """Exchange a bearer token for a signed HttpOnly session cookie.

    Audit H-02: the response no longer echoes the submitted bearer.
    The SPA already has it (the user just pasted it) and won't need
    it again — MCP calls now flow through the same-origin proxy at
    `/api/mcp/<path>` using the cookie session.

    Spec 023 FR-002: when an account-authenticated cookie is present
    on the request, the existing sid is rebound (single-sid invariant
    from H-02) AND an ``account_participants`` join row is inserted so
    ``GET /me/sessions`` reports this session under the account.
    """
    auth_service = getattr(request.app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(503, "Auth service not available")
    participant = await _authenticate_or_raise(auth_service, body.token, request)
    store = _resolve_session_store(request)
    account_sid_entry = await _resolve_existing_account_session(store, sacp_ui_token)
    if account_sid_entry is not None:
        await _bind_participant_to_account(request, account_sid_entry, participant, body.token)
        return _login_response(participant)
    sid = await store.create(participant.id, participant.session_id, body.token)
    _set_session_cookie(response, request, sid)
    return _login_response(participant)


async def _resolve_existing_account_session(
    store: SessionStore,
    cookie_value: str | None,
) -> SessionEntry | None:
    """Resolve the request's account-cookie sid → SessionEntry, or None.

    Returns ``None`` when the cookie is absent, the signature fails,
    the sid is unknown, or the entry is a legacy token-paste session
    (no ``account_id``) — only an existing account session triggers
    the spec 023 binding path.
    """
    if not cookie_value:
        return None
    try:
        sid = _parse_cookie_value(cookie_value)
    except HTTPException:
        return None
    entry = await store.get(sid)
    if entry is None or entry.account_id is None:
        return None
    return entry


async def _bind_participant_to_account(
    request: Request,
    entry: SessionEntry,
    participant: Participant,
    bearer: str,
) -> None:
    """Insert account_participants and rebind the existing sid (FR-002, FR-016)."""
    account_repo = getattr(request.app.state, "account_repo", None)
    if account_repo is not None:
        with contextlib.suppress(Exception):
            # Uniqueness collision (already linked) is the expected
            # benign case; any other repo failure stays visible upstream
            # via subsequent reads, so swallow here and rebind anyway.
            await account_repo.link_participant_to_account(
                account_id=entry.account_id,
                participant_id=participant.id,
            )
    await request.app.state.session_store.rebind_account_session(
        sid=entry.sid,
        participant_id=participant.id,
        session_id=participant.session_id,
        bearer=bearer,
    )


def _login_response(participant: Participant) -> dict:
    return {
        "participant_id": participant.id,
        "session_id": participant.session_id,
        "role": participant.role,
        "expires_in": COOKIE_MAX_AGE_SECONDS,
    }


async def _authenticate_or_raise(
    auth_service: object,
    token: str,
    request: Request,
) -> Participant:
    """Call AuthService.authenticate and translate errors to HTTPException."""
    client_ip = extract_client_ip(request)
    try:
        return await auth_service.authenticate(token, client_ip)  # type: ignore[attr-defined]
    except (AuthRequiredError, TokenInvalidError):
        raise HTTPException(401, "Invalid token") from None
    except TokenExpiredError:
        raise HTTPException(401, "Token expired") from None
    except IPBindingMismatchError:
        # Generic detail only — the underlying exception carries the bound IP
        # and the request IP for operator-side forensic logging, but echoing
        # them in the HTTP response would hand a stolen-token replay attempt
        # the legitimate user's bound IP. Mirrors src/mcp_server/middleware.py.
        raise HTTPException(403, "IP binding mismatch") from None


def _set_session_cookie(response: Response, request: Request, sid: str) -> None:
    """Issue the HttpOnly + Secure + SameSite=Strict session cookie.

    Secure flag is auto-detected from the request scheme so a
    LAN/HTTP deployment isn't silently broken. See `_secure_cookie_flag`.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=_make_cookie_value(sid),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookie_flag(request),
        samesite="strict",
        path="/",
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    sacp_ui_token: Annotated[str | None, Cookie()] = None,
) -> dict:
    """Drop the server-side session entry and clear the cookie."""
    if sacp_ui_token:
        try:
            sid = _parse_cookie_value(sacp_ui_token)
        except HTTPException:
            sid = None
        if sid:
            await _resolve_session_store(request).delete(sid)
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_secure_cookie_flag(request),
        samesite="strict",
    )
    return {"status": "logged_out"}


_INACTIVE_STATUSES = frozenset({"removed", "offline", "reset"})


async def get_current_session_entry(
    request: Request,
    sacp_ui_token: Annotated[str | None, Cookie()] = None,
) -> SessionEntry:
    """FastAPI dependency: resolve the cookie sid → server-side entry.

    Returns the raw `SessionEntry` (which carries the bearer). The MCP
    proxy uses this to attach the bearer to upstream requests without
    ever exposing it to JS.
    """
    if not sacp_ui_token:
        raise HTTPException(401, "Not authenticated")
    sid = _parse_cookie_value(sacp_ui_token)
    entry = await _resolve_session_store(request).get(sid)
    if entry is None:
        raise HTTPException(401, "Session expired")
    return entry


async def get_current_ui_participant(
    request: Request,
    entry: Annotated[SessionEntry, Depends(get_current_session_entry)],
) -> Participant:
    """FastAPI dependency: resolve the cookie + sid to a Participant row.

    Re-validates the stored bearer + IP binding on every request. The
    sid lookup is cheap, but a bearer rotated via ``rotate_token``,
    revoked via ``revoke_token``, or whose participant was removed
    must fail closed immediately rather than grant access until the
    cookie TTL elapses.
    """
    auth_service = getattr(request.app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(503, "Auth service not available")
    participant = await _authenticate_or_raise(auth_service, entry.bearer, request)
    if participant.session_id != entry.session_id:
        raise HTTPException(401, "Cookie does not match a current participant")
    if participant.status in _INACTIVE_STATUSES:
        raise HTTPException(401, "Participant is no longer active")
    return participant


UiParticipant = Annotated[Participant, Depends(get_current_ui_participant)]


@router.get("/me")
async def whoami(request: Request, participant: UiParticipant) -> dict:
    """Restore session state on page refresh.

    Audit H-02: the bearer is no longer returned to JS. MCP tool calls
    now go through the same-origin proxy at `/api/mcp/<path>`, which
    attaches the server-side bearer from the session store. The SPA
    consequently never needs the bearer in JS memory.

    Spec 021 T041 / FR-010: three additive top-level fields surface the
    participant's effective register state — ``register_slider``
    (1-5), ``register_preset`` (one of: direct, conversational,
    balanced, technical, academic), and ``register_source`` (one of:
    session, participant_override). ``register_source`` is the FR-010
    two-value enum: when no ``session_register`` row exists or no
    override applies, the env-default fallback is reported as
    ``session``. Operators auditing whether the facilitator explicitly
    set a value MUST consult the audit log for ``session_register_changed``
    rather than relying on this field.

    The fields are computed best-effort: a resolver failure logs and
    falls through to the env-default reading rather than failing the
    whole ``/me`` probe (the page must still load on a transient DB
    hiccup so the SPA can recover).
    """
    register_repo = getattr(request.app.state, "register_repo", None)
    register_slider, register_preset, register_source = await _me_register_fields(
        register_repo,
        participant.id,
        participant.session_id,
    )
    return {
        "participant_id": participant.id,
        "session_id": participant.session_id,
        "role": participant.role,
        "expires_in": COOKIE_MAX_AGE_SECONDS,
        "register_slider": register_slider,
        "register_preset": register_preset,
        "register_source": register_source,
    }


async def _me_register_fields(
    register_repo: object | None,
    participant_id: str,
    session_id: str,
) -> tuple[int, str, str]:
    """Resolve the three /me register fields, with env-default fallback.

    When the register repo is wired and the resolver succeeds, returns
    the live values per FR-010. When the repo is missing (test rigs that
    never wired ``app.state.register_repo``) OR the resolver raises
    (transient DB hiccup), falls back to the env default — /me must
    keep returning a valid payload so the SPA can recover.
    """
    from src.prompts.register_presets import preset_for_slider
    from src.repositories.register_repo import register_default_from_env

    if register_repo is not None:
        try:
            slider, preset, source = await register_repo.resolve_register(
                participant_id=participant_id,
                session_id=session_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "register resolver failed for /me participant=%s session=%s; "
                "falling back to env default",
                participant_id,
                session_id,
            )
        else:
            return slider, preset.name, source
    default = register_default_from_env()
    return default, preset_for_slider(default).name, "session"
