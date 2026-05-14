# SPDX-License-Identifier: AGPL-3.0-or-later
"""CIMD fetch + client registration. Spec 030 Phase 4 FR-073, FR-088."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse, urlunparse

import asyncpg
import httpx

_CIMD_MAX_BYTES = 256 * 1024
_CIMD_TIMEOUT_SECONDS = 10.0
_CIMD_REQUIRED_FIELDS = {"redirect_uris", "client_name"}

# Cloud-provider instance metadata service addresses that must never be
# reachable from a CIMD fetch even though they fall outside the standard
# private-address blocks `ipaddress.is_private` covers.
_CIMD_BLOCKED_LITERAL_HOSTS = frozenset(
    {
        "169.254.169.254",
        "fd00:ec2::254",
        "metadata.google.internal",
    }
)

_INSERT_CLIENT_SQL = """
    INSERT INTO oauth_clients
        (client_id, cimd_url, cimd_content, redirect_uris, allowed_scopes,
         registration_status, registered_at)
    VALUES ($1, $2, $3, $4, $5, 'approved', $6)
    RETURNING client_id
"""


async def fetch_and_validate_cimd(url: str, allowed_hosts: list[str]) -> dict:
    """Fetch + validate a CIMD document. Raises ValueError on any failure.

    SSRF defence: the URL must use https (http is rejected outside test mode),
    the hostname must resolve only to public, routable addresses, and known
    metadata-service literals are unconditionally blocked. Redirects are
    disabled at the transport so a redirect to an internal host cannot bypass
    the pre-fetch resolution check. The connection is pinned to the IP
    selected during pre-fetch resolution so a DNS-rebinding attacker cannot
    swap in an internal address between the safety check and the fetch; the
    original hostname is preserved for the Host header and TLS SNI/cert
    validation.
    """
    parsed = urlparse(url)
    allow_http = os.environ.get("SACP_OAUTH_CIMD_ALLOW_HTTP", "").lower() in {"1", "true", "yes"}
    valid_schemes = ("http", "https") if allow_http else ("https",)
    if parsed.scheme not in valid_schemes:
        raise ValueError(f"CIMD URL must use https; got {parsed.scheme!r}")

    host = parsed.hostname or ""
    if not host:
        raise ValueError("CIMD URL must include a hostname")

    if allowed_hosts and not any(host == h or host.endswith("." + h) for h in allowed_hosts):
        raise ValueError(f"CIMD host {host!r} not in allowed list")

    safe_ip = await _enforce_ssrf_safe_target(host)
    pinned_url = _pin_url_to_ip(parsed, safe_ip)
    host_header = f"{host}:{parsed.port}" if parsed.port else host

    try:
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=_CIMD_TIMEOUT_SECONDS
        ) as client:
            resp = await client.get(  # noqa: S113 -- timeout set on the client
                pinned_url,
                headers={"Host": host_header},
                extensions={"sni_hostname": host},
            )
    except httpx.TooManyRedirects as exc:
        raise ValueError("CIMD URL redirect chain too long") from exc
    except httpx.TimeoutException as exc:
        raise ValueError("CIMD fetch timed out") from exc
    except Exception as exc:
        raise ValueError("CIMD fetch failed") from exc

    if resp.status_code != 200:
        raise ValueError(f"CIMD endpoint returned HTTP {resp.status_code}")

    raw = resp.content
    if len(raw) > _CIMD_MAX_BYTES:
        raise ValueError(f"CIMD document exceeds {_CIMD_MAX_BYTES} byte limit")

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"CIMD document is not valid JSON: {exc}") from exc

    if not isinstance(doc, dict):
        raise ValueError("CIMD document must be a JSON object")

    missing = _CIMD_REQUIRED_FIELDS - set(doc.keys())
    if missing:
        raise ValueError(f"CIMD document missing required fields: {missing}")

    redirect_uris = doc.get("redirect_uris", [])
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise ValueError("CIMD redirect_uris must be a non-empty list")

    return doc


async def register_client(
    conn: asyncpg.Connection,
    cimd_url: str,
    cimd_content: dict,
) -> str:
    """Insert an oauth_clients row; return client_id."""
    from src.mcp_protocol.auth.scope_grant import SCOPE_VOCABULARY

    client_id = uuid.uuid4().hex
    redirect_uris = cimd_content.get("redirect_uris", [])
    raw_scope = cimd_content.get("scope", "")
    requested_scopes = raw_scope.split() if isinstance(raw_scope, str) and raw_scope else []
    if requested_scopes:
        allowed_scopes = list(SCOPE_VOCABULARY & set(requested_scopes))
    else:
        allowed_scopes = list(SCOPE_VOCABULARY)
    now = datetime.now(tz=UTC)
    row = await conn.fetchrow(
        _INSERT_CLIENT_SQL,
        client_id,
        cimd_url,
        json.dumps(cimd_content),
        redirect_uris,
        allowed_scopes,
        now,
    )
    return row["client_id"]


def _allowed_hosts_from_env() -> list[str]:
    raw = os.environ.get("SACP_OAUTH_CIMD_ALLOWED_HOSTS", "")
    if not raw.strip():
        return []
    return [h.strip() for h in raw.split(",") if h.strip()]


def _pin_url_to_ip(parsed, ip: str) -> str:
    """Substitute the validated IP literal for the hostname in the URL.

    The caller sends the original hostname back via the Host header and the
    `sni_hostname` request extension so vhost routing and TLS cert validation
    still see the user-facing name; only the IP-layer destination is pinned.
    """
    netloc = f"[{ip}]" if ":" in ip else ip
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


async def _enforce_ssrf_safe_target(host: str) -> str:
    """Resolve `host`, reject internal targets, and return a safe IP literal.

    Runs `getaddrinfo` in a worker thread so the event loop is not blocked.
    Every returned address must be a global, routable IP — any private,
    loopback, link-local, multicast, reserved, or unspecified address aborts
    the fetch with a fixed-form ValueError that carries no resolver details.
    Returns the first safe address so the caller can pin the connection and
    defeat DNS-rebinding TOCTOU.
    """
    if host.lower() in _CIMD_BLOCKED_LITERAL_HOSTS:
        raise ValueError("CIMD URL targets a blocked address")

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None, 0, socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("CIMD URL hostname does not resolve") from exc

    if not infos:
        raise ValueError("CIMD URL hostname does not resolve")

    safe_ip: str | None = None
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            raise ValueError("CIMD URL hostname does not resolve")
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise ValueError("CIMD URL hostname resolved to an invalid address") from exc
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("CIMD URL must not resolve to an internal address")
        if safe_ip is None:
            safe_ip = ip_str

    if safe_ip is None:
        raise ValueError("CIMD URL hostname does not resolve")
    return safe_ip
