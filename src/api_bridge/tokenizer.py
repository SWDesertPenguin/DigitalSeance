# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-provider tokenizer adapters for budget + context-assembly accuracy.

The bridge layer needs to count tokens against the *target* model's
tokenizer, not against a single in-process estimator. Tokenizer drift
between providers is well-documented (DEV Community 2026 cross-provider
study; see local research bundle): English prose lands within 5–15%
across providers, code-heavy and non-Latin content drifts 20–30%+.
This module surfaces a small Protocol so context assembly and budget
tracking can resolve the right adapter per participant and stop
relying on the `len(text) // 4` rough cut.

Three adapters ship in Phase 1:

  - OpenAI: tiktoken local (cl100k_base for gpt-3.5/gpt-4, o200k_base
    for gpt-4o and o-series). No network. Always-on.
  - Anthropic: tiktoken cl100k_base × 1.10 multiplier as the default
    runtime path; the anthropic-SDK count_tokens API is the
    full-precision reconciliation path (lazy-imported; absence is
    diagnosed at reconcile time, not at module import).
  - Gemini: tiktoken cl100k_base × 0.95 multiplier as the default
    runtime path; google-generativeai countTokens API is the
    reconciliation path (lazy-imported, same diagnosis pattern).

The default-runtime / API-reconcile split is deliberate: every
hot-path call returns instantly without a network round-trip, and the
end-of-session or facilitator-triggered reconcile re-walks recent
turns through the API path to produce a drift report. LiteLLM's
post-call cost remains the truth source for billing (003 §FR-028); the
adapter is the truth source for *budget allocation decisions made
before the dispatch fires*.

Compression callers leave headroom around the adapter count via the
following over-compression margin convention (consumers' contract,
not enforced inside the tokenizer):

  - English prose: 10–15%
  - Code or non-Latin scripts: 20–25%

These guidelines back the Phase 3 hard-compression hooks that haven't
landed yet; they're documented here so the Phase 3 PR can wire them
without re-deriving the numbers.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import asyncpg

# Empirical fallback multipliers from the local research bundle's
# cross-provider tokenizer study (English prose; code/non-Latin
# content drifts wider — callers add per-class margin).
_ANTHROPIC_FALLBACK_MULTIPLIER = 1.10
_GEMINI_FALLBACK_MULTIPLIER = 0.95


@runtime_checkable
class TokenizerAdapter(Protocol):
    """Per-target-model tokenizer interface."""

    def count_tokens(self, content: str) -> int:
        """Return the integer token count for `content`."""
        ...

    def truncate_to_tokens(self, content: str, n: int) -> str:
        """Return the longest prefix of `content` that fits within `n` tokens."""
        ...

    def get_tokenizer_name(self) -> str:
        """Identifier suitable for log lines and reconciliation reports."""
        ...


class OpenAITokenizer:
    """tiktoken-backed adapter; encoding chosen by model name."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._encoding = _resolve_openai_encoding(model)

    def count_tokens(self, content: str) -> int:
        return len(self._encoding.encode(content))

    def truncate_to_tokens(self, content: str, n: int) -> str:
        if n <= 0 or not content:
            return ""
        ids = self._encoding.encode(content)[:n]
        return self._encoding.decode(ids)

    def get_tokenizer_name(self) -> str:
        return f"openai:{self._encoding.name}"


class AnthropicTokenizer:
    """tiktoken cl100k × 1.10 by default; anthropic SDK path on reconcile."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._encoding = _cl100k()

    def count_tokens(self, content: str) -> int:
        raw = len(self._encoding.encode(content))
        return int(raw * _ANTHROPIC_FALLBACK_MULTIPLIER)

    def truncate_to_tokens(self, content: str, n: int) -> str:
        if n <= 0 or not content:
            return ""
        budget = max(int(n / _ANTHROPIC_FALLBACK_MULTIPLIER), 1)
        ids = self._encoding.encode(content)[:budget]
        return self._encoding.decode(ids)

    def get_tokenizer_name(self) -> str:
        return "anthropic:fallback-cl100k-x1.10"

    def count_tokens_via_api(self, content: str, *, api_key: str) -> int:
        """Full-precision count via anthropic SDK. Raises if SDK missing."""
        try:
            import anthropic  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("anthropic SDK not installed; reconciliation requires it") from exc
        client = anthropic.Anthropic(api_key=api_key)
        result = client.messages.count_tokens(
            model=self._model,
            messages=[{"role": "user", "content": content}],
        )
        return int(result.input_tokens)


class GeminiTokenizer:
    """tiktoken cl100k × 0.95 by default; google SDK path on reconcile."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._encoding = _cl100k()

    def count_tokens(self, content: str) -> int:
        raw = len(self._encoding.encode(content))
        return max(int(raw * _GEMINI_FALLBACK_MULTIPLIER), 0)

    def truncate_to_tokens(self, content: str, n: int) -> str:
        if n <= 0 or not content:
            return ""
        budget = max(int(n / _GEMINI_FALLBACK_MULTIPLIER), 1)
        ids = self._encoding.encode(content)[:budget]
        return self._encoding.decode(ids)

    def get_tokenizer_name(self) -> str:
        return "gemini:fallback-cl100k-x0.95"

    def count_tokens_via_api(self, content: str, *, api_key: str) -> int:
        """Full-precision count via google-generativeai SDK. Raises if missing."""
        try:
            import google.generativeai as genai  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "google-generativeai SDK not installed; reconciliation requires it"
            ) from exc
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(self._model)
        result = model.count_tokens(content)
        return int(result.total_tokens)


class _DefaultTokenizer:
    """Generic estimator for system content (no per-participant scope)."""

    def __init__(self) -> None:
        self._encoding = _cl100k()

    def count_tokens(self, content: str) -> int:
        return len(self._encoding.encode(content))

    def truncate_to_tokens(self, content: str, n: int) -> str:
        if n <= 0 or not content:
            return ""
        ids = self._encoding.encode(content)[:n]
        return self._encoding.decode(ids)

    def get_tokenizer_name(self) -> str:
        return "default:cl100k"


def get_tokenizer_for_model(model: str) -> TokenizerAdapter:
    """Resolve a tokenizer adapter from a LiteLLM model string."""
    if model.startswith(("anthropic/", "claude-")):
        return AnthropicTokenizer(model)
    if model.startswith(("gemini/", "google/", "vertex_ai/")):
        return GeminiTokenizer(model)
    if model.startswith(("openai/", "gpt-", "o1-", "o3-", "o4-")):
        return OpenAITokenizer(model)
    return _DefaultTokenizer()


_PARTICIPANT_CACHE: dict[str, TokenizerAdapter] = {}


async def get_tokenizer_for_participant(
    pool: asyncpg.Pool,
    participant_id: str,
) -> TokenizerAdapter:
    """Resolve a participant's tokenizer; cached for process lifetime."""
    cached = _PARTICIPANT_CACHE.get(participant_id)
    if cached is not None:
        return cached
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT model FROM participants WHERE id = $1",
            participant_id,
        )
    model = row["model"] if row else ""
    adapter = get_tokenizer_for_model(model)
    _PARTICIPANT_CACHE[participant_id] = adapter
    return adapter


_DEFAULT_INSTANCE: _DefaultTokenizer | None = None


def default_estimator() -> TokenizerAdapter:
    """Tokenizer for orchestrator-generated content (no participant scope).

    Returns a process-lifetime singleton so callers in hot paths
    (message persistence, system-content sizing) don't re-create the
    tiktoken encoding wrapper on every call.
    """
    global _DEFAULT_INSTANCE
    if _DEFAULT_INSTANCE is None:
        _DEFAULT_INSTANCE = _DefaultTokenizer()
    return _DEFAULT_INSTANCE


def clear_participant_cache() -> None:
    """Reset the per-participant adapter cache (test isolation)."""
    _PARTICIPANT_CACHE.clear()


class ReconciliationReport:
    """Per-participant drift summary returned by `reconcile_budget`."""

    __slots__ = ("participant_id", "tokenizer_name", "samples", "cumulative_drift_pct")

    def __init__(
        self,
        *,
        participant_id: str,
        tokenizer_name: str,
        samples: list[dict[str, Any]],
        cumulative_drift_pct: float,
    ) -> None:
        self.participant_id = participant_id
        self.tokenizer_name = tokenizer_name
        self.samples = samples
        self.cumulative_drift_pct = cumulative_drift_pct


async def reconcile_budget(
    pool: asyncpg.Pool,
    participant_id: str,
    *,
    api_key: str,
    sample_size: int = 25,
) -> ReconciliationReport:
    """Recompute recent turns via the API path; report drift vs stored counts.

    Phase 1 ships the function; Phase 3 wires the MCP tool that lets a
    facilitator request a reconciliation on demand.
    """
    adapter = await get_tokenizer_for_participant(pool, participant_id)
    rows = await _fetch_recent_messages(pool, participant_id, sample_size)
    samples, drift_total, count_total = _build_samples(adapter, rows, api_key)
    pct = (drift_total / count_total * 100) if count_total > 0 else 0.0
    return ReconciliationReport(
        participant_id=participant_id,
        tokenizer_name=adapter.get_tokenizer_name(),
        samples=samples,
        cumulative_drift_pct=pct,
    )


async def _fetch_recent_messages(
    pool: asyncpg.Pool,
    participant_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT turn_number, content, token_count FROM messages "
            "WHERE speaker_id = $1 ORDER BY turn_number DESC LIMIT $2",
            participant_id,
            limit,
        )
    return [dict(r) for r in rows]


def _build_samples(
    adapter: TokenizerAdapter,
    rows: list[dict[str, Any]],
    api_key: str,
) -> tuple[list[dict[str, Any]], int, int]:
    """Build per-row drift samples and totals."""
    samples: list[dict[str, Any]] = []
    drift_total = 0
    count_total = 0
    for row in rows:
        api_count = _api_count(adapter, row["content"], api_key)
        stored = int(row["token_count"] or 0)
        delta = api_count - stored
        drift_total += abs(delta)
        count_total += api_count
        samples.append(
            {
                "turn_number": row["turn_number"],
                "stored": stored,
                "api_count": api_count,
                "delta": delta,
            }
        )
    return samples, drift_total, count_total


def _api_count(adapter: TokenizerAdapter, content: str, api_key: str) -> int:
    """Dispatch to the adapter's API path when available; else fallback."""
    if isinstance(adapter, AnthropicTokenizer | GeminiTokenizer):
        try:
            return adapter.count_tokens_via_api(content, api_key=api_key)
        except RuntimeError:
            return adapter.count_tokens(content)
    return adapter.count_tokens(content)


def _resolve_openai_encoding(model: str) -> Any:
    """Pick the right tiktoken encoding for an OpenAI model string."""
    import tiktoken

    bare = model.removeprefix("openai/")
    if bare.startswith(("gpt-4o", "o1", "o3", "o4")):
        return tiktoken.get_encoding("o200k_base")
    return tiktoken.get_encoding("cl100k_base")


def _cl100k() -> Any:
    """tiktoken cl100k_base — shared across non-OpenAI fallback paths."""
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")
