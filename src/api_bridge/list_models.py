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
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

_TIMEOUT_S = 10.0


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
        if bare:
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
    """Fetch local Ollama tags. Endpoint required, key ignored."""
    if not api_endpoint:
        raise ListModelsError(400, "api_endpoint required for ollama (e.g. http://localhost:11434)")
    base = api_endpoint.rstrip("/")
    resp = await client.get(f"{base}/api/tags")
    _raise_for_status("ollama", resp)
    return [
        ModelInfo(model=f"ollama_chat/{m['name']}", display=m["name"])
        for m in resp.json().get("models", [])
    ]
