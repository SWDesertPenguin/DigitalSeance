# SPDX-License-Identifier: AGPL-3.0-or-later

"""Live model enumeration per provider.

Operators previously had to type model strings by hand into the AddAI
dialog. Round07 hit a 429 because someone typed ``gemini-2.0-flash`` —
a model whose free-tier quota Google removed on 2026-04-25. Fetching
the live list at the moment the operator pastes an API key surfaces
exactly which models that key can reach.

Each helper hits the provider's REST API directly via httpx (LiteLLM
has no introspection helper). Keys are passed in headers / query
params per provider convention. Returned strings are LiteLLM-prefixed
so the UI can drop them straight into the existing model field.

The Ollama branch is the SSRF-sensitive one: ``api_endpoint`` is
operator-supplied, the call is server-side, and the response body
flows back to the caller. We allowlist host categories (loopback +
RFC1918 private), block link-local / IMDS / public, and pin the
connection to the validated IP so DNS rebinding can't swap the host
between validation and connect.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

_TIMEOUT_S = 10.0

# Ollama endpoint allowlist — by user policy (option A): loopback +
# RFC1918 private (covers host.docker.internal which resolves into
# the Docker bridge LAN). Block link-local (kills IMDS at 169.254.*),
# multicast, reserved, unspecified, and public IPs. Public reachability
# would let an authenticated participant pivot SACP into internal-network
# scanning or exfiltration.
_ALLOWED_OLLAMA_SCHEMES = ("http", "https")


@dataclass(frozen=True)
class ModelInfo:
    """One row in the dropdown."""

    model: str  # LiteLLM-prefixed: e.g. "anthropic/claude-haiku-4-5-20251001"
    display: str  # Humanized: e.g. "claude-haiku-4-5-20251001"


class ListModelsError(Exception):
    """Wraps any provider failure (auth, network, parse) for the caller."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


async def list_provider_models(
    *,
    provider: str,
    api_key: str,
    api_endpoint: str | None = None,
) -> list[ModelInfo]:
    """Return chat-capable models for the given provider key."""
    handlers = {
        "anthropic": _list_anthropic,
        "openai": _list_openai,
        "gemini": _list_gemini,
        "groq": _list_groq,
        "ollama": _list_ollama,
    }
    handler = handlers.get(provider)
    if handler is None:
        raise ListModelsError(400, f"Unsupported provider: {provider}")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            return await handler(client, api_key, api_endpoint)
    except ListModelsError:
        raise
    except httpx.RequestError as exc:
        raise ListModelsError(502, f"Could not reach {provider}: {exc}") from exc


def _raise_for_status(provider: str, resp: httpx.Response) -> None:
    """Translate provider HTTP failures into ListModelsError."""
    if resp.status_code == 200:
        return
    if resp.status_code in (401, 403):
        raise ListModelsError(400, f"Invalid API key for {provider}")
    if resp.status_code == 429:
        raise ListModelsError(429, f"{provider} rate-limited the model-list request")
    raise ListModelsError(502, f"{provider} returned HTTP {resp.status_code}")


async def _list_anthropic(
    client: httpx.AsyncClient,
    api_key: str,
    _endpoint: str | None,
) -> list[ModelInfo]:
    """Fetch Anthropic chat models. /v1/models returns chat-only."""
    resp = await client.get(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
    )
    _raise_for_status("anthropic", resp)
    return [
        ModelInfo(model=f"anthropic/{m['id']}", display=m["id"])
        for m in resp.json().get("data", [])
    ]


# OpenAI's /v1/models returns embeddings, TTS, Whisper, image gen, etc.
# Filter to chat-capable prefixes — keeps the dropdown short and avoids
# operators picking an embeddings model by accident.
_OPENAI_CHAT_PREFIXES = ("gpt-", "o1-", "o3-", "chatgpt-")


async def _list_openai(
    client: httpx.AsyncClient,
    api_key: str,
    _endpoint: str | None,
) -> list[ModelInfo]:
    """Fetch OpenAI chat models, filtered."""
    resp = await client.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    _raise_for_status("openai", resp)
    out: list[ModelInfo] = []
    for m in resp.json().get("data", []):
        mid = m.get("id", "")
        if mid.startswith(_OPENAI_CHAT_PREFIXES):
            out.append(ModelInfo(model=mid, display=mid))
    return out


# Free-tier quota for the 2.0-flash family was zeroed on 2026-04-25; Google
# routes 2.0-flash-lite-001 calls into the same bucket, so any 2.0-* dispatch
# 429s on a fresh key. Hide the family from the picker so operators don't
# pick a model that fails on first turn.
_GEMINI_BLOCKED_PREFIXES = ("gemini-2.0-",)


async def _list_gemini(
    client: httpx.AsyncClient,
    api_key: str,
    _endpoint: str | None,
) -> list[ModelInfo]:
    """Fetch Gemini models that support generateContent."""
    resp = await client.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key},
    )
    _raise_for_status("gemini", resp)
    out: list[ModelInfo] = []
    for m in resp.json().get("models", []):
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        # name field is "models/gemini-2.5-flash-lite" — strip the prefix.
        raw = m.get("name", "")
        bare = raw.removeprefix("models/")
        if not bare:
            continue
        if bare.startswith(_GEMINI_BLOCKED_PREFIXES):
            continue
        out.append(ModelInfo(model=f"gemini/{bare}", display=bare))
    return out


async def _list_groq(
    client: httpx.AsyncClient,
    api_key: str,
    _endpoint: str | None,
) -> list[ModelInfo]:
    """Fetch Groq models. OpenAI-compatible /openai/v1/models."""
    resp = await client.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    _raise_for_status("groq", resp)
    return [
        ModelInfo(model=f"groq/{m['id']}", display=m["id"]) for m in resp.json().get("data", [])
    ]


async def _list_ollama(
    client: httpx.AsyncClient,
    _api_key: str,
    api_endpoint: str | None,
) -> list[ModelInfo]:
    """Fetch local Ollama tags. Endpoint required, key ignored, host allowlisted."""
    if not api_endpoint:
        raise ListModelsError(400, "api_endpoint required for ollama (e.g. http://localhost:11434)")
    safe_base = await _validate_and_pin_ollama_endpoint(api_endpoint)
    resp = await client.get(f"{safe_base}/api/tags")
    _raise_for_status("ollama", resp)
    return [
        ModelInfo(model=f"ollama_chat/{m['name']}", display=m["name"])
        for m in resp.json().get("models", [])
    ]


async def _validate_and_pin_ollama_endpoint(api_endpoint: str) -> str:
    """Allowlist scheme + host category, return URL pinned to validated IP."""
    parsed = urlparse(api_endpoint)
    if parsed.scheme not in _ALLOWED_OLLAMA_SCHEMES:
        raise ListModelsError(400, f"Unsupported scheme '{parsed.scheme}' (http/https only)")
    host = parsed.hostname
    if not host:
        raise ListModelsError(400, "api_endpoint missing host")
    ip = await _resolve_and_validate_host(host)
    host_str = f"[{ip}]" if isinstance(ip, ipaddress.IPv6Address) else str(ip)
    port_str = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host_str}{port_str}".rstrip("/")


async def _resolve_and_validate_host(
    host: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Resolve hostname; reject if any answer is in a blocked range."""
    loop = asyncio.get_event_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ListModelsError(502, f"Could not resolve '{host}': {exc}") from exc
    if not infos:
        raise ListModelsError(502, f"No address records for '{host}'")
    addrs = [_strip_zone(info[4][0]) for info in infos]
    parsed_ips = [ipaddress.ip_address(a) for a in addrs]
    for ip in parsed_ips:
        _reject_blocked_ip(host, ip)
    return parsed_ips[0]


def _strip_zone(addr: str) -> str:
    """Drop IPv6 zone identifier ('fe80::1%eth0' -> 'fe80::1')."""
    return addr.split("%", 1)[0]


def _reject_blocked_ip(host: str, ip: ipaddress._BaseAddress) -> None:
    """Raise if an IP is in a category we refuse to reach.

    Order matters at two points:

    1. ``is_link_local`` is checked BEFORE ``is_private``. Python's
       ``is_private`` follows IANA's special-purpose registry, which
       *includes* 169.254.0.0/16 — a naive ``is_private`` allow would
       let IMDS through on cloud deployments.
    2. The loopback / private allow comes BEFORE the
       ``is_reserved`` reject. Python marks IPv6 loopback (``::1``) as
       *both* ``is_loopback=True`` and ``is_reserved=True`` (per
       IANA's ``::/8`` allocation), so a naive ``is_reserved`` reject
       would block local Ollama on IPv6.
    """
    if ip.is_link_local:
        # 169.254.0.0/16 — IMDS lives here on AWS, GCP, Azure.
        raise ListModelsError(400, f"link-local address blocked for '{host}'")
    if ip.is_loopback or ip.is_private:
        return
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        raise ListModelsError(400, f"blocked address category for '{host}'")
    raise ListModelsError(400, f"public address not allowed for '{host}'")
