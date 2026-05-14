# SPDX-License-Identifier: AGPL-3.0-or-later
"""ES256 JWT signing and verification. Spec 030 Phase 4 FR-088, FR-097."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from src.mcp_protocol.auth import token_cache


def _load_private_key(path: str):  # type: ignore[no-untyped-def]
    raw = open(path, "rb").read()  # noqa: SIM115
    return load_pem_private_key(raw, password=None)


def _load_public_key(path: str):  # type: ignore[no-untyped-def]
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    raw = open(path, "rb").read()  # noqa: SIM115
    return load_pem_public_key(raw)


def _get_private_key():  # type: ignore[no-untyped-def]
    path = os.environ.get("SACP_OAUTH_SIGNING_KEY_PATH", "")
    if not path:
        raise RuntimeError("SACP_OAUTH_SIGNING_KEY_PATH not set")
    return _load_private_key(path)


def _get_public_keys() -> list:  # type: ignore[no-untyped-def]
    keys = []
    primary = os.environ.get("SACP_OAUTH_SIGNING_KEY_PATH", "")
    if primary:
        pk = _load_private_key(primary)
        keys.append(pk.public_key())
    prev = os.environ.get("SACP_OAUTH_PREVIOUS_SIGNING_KEY_PATH", "")
    if prev:
        import contextlib

        try:
            pk2 = _load_private_key(prev)
            keys.append(pk2.public_key())
        except Exception:
            with contextlib.suppress(Exception):
                keys.append(_load_public_key(prev))
    return keys


def _access_token_ttl() -> int:
    val = os.environ.get("SACP_OAUTH_ACCESS_TOKEN_TTL_MINUTES", "60")
    try:
        return max(5, min(1440, int(val)))
    except (ValueError, TypeError):
        return 60


def sign_access_token(
    sub: str,
    client_id: str,
    scope: list[str],
    auth_time: str,
    session_id: str | None = None,
) -> str:
    """Issue a signed ES256 JWT access token per FR-097."""
    private_key = _get_private_key()
    now = datetime.now(tz=UTC)
    ttl = _access_token_ttl()
    jti = uuid.uuid4().hex
    payload: dict = {
        "sub": sub,
        "client_id": client_id,
        "scope": scope,
        "auth_time": auth_time,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "jti": jti,
    }
    if session_id is not None:
        payload["session_id"] = session_id
    return jwt.encode(payload, private_key, algorithm="ES256")


def verify_access_token(token: str) -> dict:
    """Verify JWT signature and expiry; check revocation cache.

    Raises jwt.InvalidTokenError on any failure.
    """
    public_keys = _get_public_keys()
    if not public_keys:
        raise jwt.InvalidTokenError("no signing keys configured")

    last_exc: Exception | None = None
    for key in public_keys:
        try:
            payload = jwt.decode(token, key, algorithms=["ES256"])
            break
        except jwt.InvalidTokenError as exc:
            last_exc = exc
    else:
        raise last_exc or jwt.InvalidTokenError("token verification failed")

    jti = payload.get("jti", "")
    cached = token_cache.is_revoked(jti)
    if cached is True:
        raise jwt.InvalidTokenError("token has been revoked")
    if cached is None:
        token_cache.mark_valid(jti)
    return payload
