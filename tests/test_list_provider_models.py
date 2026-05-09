# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider model-listing tests.

Mocks each provider's HTTP API via ``httpx.MockTransport`` to verify
``list_provider_models`` translates the provider response into our
``ModelInfo`` shape and that error envelopes (auth, rate limit,
network, parse) become the right ``ListModelsError`` codes.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from src.api_bridge.list_models import (
    ListModelsError,
    ModelInfo,
    list_provider_models,
)


def _mock_transport(handler):
    """Build a MockTransport that hands every request to ``handler``."""
    return httpx.MockTransport(handler)


def _patched_client(transport: httpx.MockTransport):
    """Patch httpx.AsyncClient so list_provider_models uses our mock transport."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    return patch("src.api_bridge.list_models.httpx.AsyncClient", side_effect=factory)


@pytest.mark.asyncio
async def test_list_anthropic_returns_prefixed_models():
    """Anthropic models come back prefixed with 'anthropic/'."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "sk-ant-test"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "claude-haiku-4-5-20251001"},
                    {"id": "claude-opus-4-7"},
                ]
            },
        )

    with _patched_client(_mock_transport(handler)):
        result = await list_provider_models(provider="anthropic", api_key="sk-ant-test")

    assert result == [
        ModelInfo(model="anthropic/claude-haiku-4-5-20251001", display="claude-haiku-4-5-20251001"),
        ModelInfo(model="anthropic/claude-opus-4-7", display="claude-opus-4-7"),
    ]


@pytest.mark.asyncio
async def test_list_openai_filters_to_chat_models():
    """OpenAI returns embeddings/TTS too — only chat models survive the filter."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "gpt-4o-mini"},
                    {"id": "text-embedding-3-small"},  # filtered out
                    {"id": "o1-preview"},
                    {"id": "tts-1"},  # filtered out
                    {"id": "whisper-1"},  # filtered out
                    {"id": "chatgpt-4o-latest"},
                ]
            },
        )

    with _patched_client(_mock_transport(handler)):
        result = await list_provider_models(provider="openai", api_key="sk-test")

    assert [m.model for m in result] == ["gpt-4o-mini", "o1-preview", "chatgpt-4o-latest"]


_GEMINI_RESPONSE = {
    "models": [
        {
            "name": "models/gemini-2.5-flash-lite",
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        },
        {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
        {
            "name": "models/gemini-2.0-flash-lite-001",
            "supportedGenerationMethods": ["generateContent"],
        },
    ]
}


@pytest.mark.asyncio
async def test_list_gemini_filters_to_generate_content_capable():
    """Embedding-only models drop, and 2.0-family entries are blocked.

    Google zeroed free-tier quota on the 2.0 family on 2026-04-25 and routes
    2.0-flash-lite-001 into the same bucket — both should be hidden from the
    picker so fresh keys don't pick a 429-on-arrival model.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("key") == "AIzaTest"
        return httpx.Response(200, json=_GEMINI_RESPONSE)

    with _patched_client(_mock_transport(handler)):
        result = await list_provider_models(provider="gemini", api_key="AIzaTest")

    assert [m.model for m in result] == ["gemini/gemini-2.5-flash-lite"]


@pytest.mark.asyncio
async def test_list_groq_returns_prefixed_models():
    """Groq is OpenAI-compatible; passthrough with 'groq/' prefix."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer gsk_test"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "llama-3.3-70b-versatile"},
                ]
            },
        )

    with _patched_client(_mock_transport(handler)):
        result = await list_provider_models(provider="groq", api_key="gsk_test")

    assert result == [
        ModelInfo(model="groq/llama-3.3-70b-versatile", display="llama-3.3-70b-versatile"),
    ]


@pytest.mark.asyncio
async def test_list_ollama_uses_endpoint():
    """Ollama hits {endpoint}/api/tags; loopback literal passes through."""

    def handler(request: httpx.Request) -> httpx.Response:
        # 127.0.0.1 is a literal IP — validator confirms it's loopback
        # and uses it as-is. URL rewrite only happens for hostnames.
        assert str(request.url) == "http://127.0.0.1:11434/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "llama3.2:3b"},
                    {"name": "qwen2.5:7b"},
                ]
            },
        )

    with _patched_client(_mock_transport(handler)):
        result = await list_provider_models(
            provider="ollama",
            api_key="",
            api_endpoint="http://127.0.0.1:11434",
        )

    assert [m.model for m in result] == ["ollama_chat/llama3.2:3b", "ollama_chat/qwen2.5:7b"]


@pytest.mark.asyncio
async def test_list_ollama_rejects_blank_endpoint():
    """Ollama without an endpoint is a 400, not a network error."""
    with pytest.raises(ListModelsError) as exc:
        await list_provider_models(provider="ollama", api_key="", api_endpoint=None)
    assert exc.value.status == 400
    assert "endpoint" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_list_ollama_rejects_link_local():
    """169.254.* (IMDS) is in the link-local range and must be blocked."""
    with pytest.raises(ListModelsError) as exc:
        await list_provider_models(
            provider="ollama",
            api_key="",
            api_endpoint="http://169.254.169.254:80",
        )
    assert exc.value.status == 400
    assert "link-local" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_list_ollama_rejects_public_ip():
    """Public IPs are rejected — Ollama is local-by-design."""
    with pytest.raises(ListModelsError) as exc:
        await list_provider_models(
            provider="ollama",
            api_key="",
            api_endpoint="http://8.8.8.8:11434",
        )
    assert exc.value.status == 400
    assert "public" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_list_ollama_rejects_unsupported_scheme():
    """ftp://, file://, gopher:// etc. are blocked at scheme level."""
    with pytest.raises(ListModelsError) as exc:
        await list_provider_models(
            provider="ollama",
            api_key="",
            api_endpoint="file:///etc/passwd",
        )
    assert exc.value.status == 400
    assert "scheme" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_list_ollama_accepts_rfc1918_private():
    """RFC1918 private ranges (10.*, 172.16-31.*, 192.168.*) are allowed."""

    def handler(request: httpx.Request) -> httpx.Response:
        # Already a literal IP — passes through unchanged.
        assert str(request.url) == "http://10.0.0.5:11434/api/tags"
        return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})

    with _patched_client(_mock_transport(handler)):
        result = await list_provider_models(
            provider="ollama",
            api_key="",
            api_endpoint="http://10.0.0.5:11434",
        )

    assert [m.model for m in result] == ["ollama_chat/llama3.2:3b"]


@pytest.mark.asyncio
async def test_invalid_key_becomes_400():
    """A 401 from the provider surfaces as ListModelsError(400)."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key"})

    with _patched_client(_mock_transport(handler)), pytest.raises(ListModelsError) as exc:
        await list_provider_models(provider="anthropic", api_key="sk-bad")

    assert exc.value.status == 400
    assert "Invalid API key" in exc.value.message


@pytest.mark.asyncio
async def test_network_error_becomes_502():
    """Connection refused / DNS failure surfaces as ListModelsError(502)."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with _patched_client(_mock_transport(handler)), pytest.raises(ListModelsError) as exc:
        await list_provider_models(provider="openai", api_key="sk-x")

    assert exc.value.status == 502
    assert "Could not reach openai" in exc.value.message


@pytest.mark.asyncio
async def test_unsupported_provider_is_400():
    """An unknown provider name short-circuits before any HTTP call."""
    with pytest.raises(ListModelsError) as exc:
        await list_provider_models(provider="madeup", api_key="x")
    assert exc.value.status == 400
