"""LiteLLM-backed capability lookup per spec 020 FR-011 + research.md §3 / §12.

Computes a `Capabilities` object for a given model by consulting LiteLLM's
bundled metadata + `src/api_bridge/model_limits.py`'s provider-neutral
fallback table. Applies the bounded `_PROVIDER_FAMILY_MAP` to LiteLLM's
free-form provider names so spec 016's Prometheus `provider_family` label
stays cardinality-controlled per FR-005 of that spec.

The model_limits.py module previously held an inline `import litellm`
inside `_from_litellm()`. Per FR-005's architectural test (no `import
litellm` outside `src/api_bridge/litellm/`), that helper relocates here
(T076). model_limits.py now consults `litellm_max_input_tokens()` from
this module instead.
"""

from __future__ import annotations

import logging
from typing import Any

import litellm

from src.api_bridge.adapter import Capabilities
from src.api_bridge.tokenizer import get_tokenizer_for_model

log = logging.getLogger(__name__)

# Bounded enum for spec 016's `provider_family` Prometheus label.
# Free-form LiteLLM provider names map to this set; unknown providers
# collapse to "unknown" so cardinality stays controlled.
_PROVIDER_FAMILY_MAP: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "azure": "openai",  # Azure OpenAI maps to openai family
    "vertex_ai": "gemini",  # Google Vertex maps to gemini family
    "gemini": "gemini",
    "groq": "groq",
    "ollama": "ollama",
    "ollama_chat": "ollama",
    "vllm": "vllm",
    "together_ai": "openai",  # OpenAI-compatible
    "openrouter": "openai",  # OpenAI-compatible
}

# Default temperature ranges by provider family. Conservative defaults
# match each provider's documented recommended_temperature_range.
_FAMILY_TEMP_RANGES: dict[str, tuple[float, float]] = {
    "anthropic": (0.0, 1.0),
    "openai": (0.0, 2.0),
    "gemini": (0.0, 1.0),
    "groq": (0.0, 1.0),
    "ollama": (0.0, 2.0),
    "vllm": (0.0, 2.0),
    "mock": (0.0, 1.0),
    "unknown": (0.0, 1.0),
}


def compute_capabilities(model: str) -> Capabilities:
    """Compute `Capabilities` for `model` from LiteLLM metadata + fallbacks."""
    raw_family = _raw_provider_family(model)
    family = _PROVIDER_FAMILY_MAP.get(raw_family, "unknown")
    info = _get_model_info(model)
    max_context = _max_context_tokens(info)
    tokenizer_name = _tokenizer_name(model)
    supports_tool_calling = bool(info.get("supports_function_calling", False))
    supports_streaming = bool(info.get("supports_streaming", True))
    supports_prompt_caching = bool(info.get("supports_prompt_caching", False))
    return Capabilities(
        supports_streaming=supports_streaming,
        supports_tool_calling=supports_tool_calling,
        supports_prompt_caching=supports_prompt_caching,
        max_context_tokens=max_context,
        tokenizer_name=tokenizer_name,
        recommended_temperature_range=_FAMILY_TEMP_RANGES.get(family, (0.0, 1.0)),
        provider_family=family,
    )


def litellm_max_input_tokens(model: str) -> int | None:
    """Pull max_input_tokens from LiteLLM's bundled model metadata.

    Relocated from `src/api_bridge/model_limits.py` per spec 020 T076 so
    no `litellm` import lives outside `src/api_bridge/litellm/`. Returns
    `None` for unknown models or metadata gaps; callers fall back to the
    explicit `_FALLBACK_MAX_INPUT_TOKENS` table in model_limits.py or to
    the operator-declared value.
    """
    try:
        info = litellm.get_model_info(model)
    except Exception:
        # LiteLLM raises BadRequestError / KeyError for unknown models;
        # treat all errors as "no metadata" and let the caller fall
        # through to the fallback table.
        return None
    if not isinstance(info, dict):
        return None
    raw = info.get("max_input_tokens") or info.get("max_tokens")
    if not isinstance(raw, int) or raw <= 0:
        return None
    return raw


def _raw_provider_family(model: str) -> str:
    """Best-effort provider-family lookup via LiteLLM's helper."""
    try:
        result = litellm.get_llm_provider(model)
    except Exception:
        return "unknown"
    if isinstance(result, tuple) and result:
        provider = result[0]
        if isinstance(provider, str):
            return provider
    if isinstance(result, str):
        return result
    return "unknown"


def _get_model_info(model: str) -> dict[str, Any]:
    """LiteLLM model-info dict; empty dict on unknown / metadata errors."""
    try:
        info = litellm.get_model_info(model)
    except Exception:
        return {}
    if not isinstance(info, dict):
        return {}
    return info


def _max_context_tokens(info: dict[str, Any]) -> int:
    """Read max input tokens from LiteLLM info; floor at 1024."""
    raw = info.get("max_input_tokens") or info.get("max_tokens")
    if isinstance(raw, int) and raw >= 1024:
        return raw
    return 1024  # data-model.md validation rule floor


def _tokenizer_name(model: str) -> str:
    """Resolve the tokenizer-family identifier for `model`."""
    try:
        adapter = get_tokenizer_for_model(model)
    except Exception:
        return "unknown"
    try:
        return adapter.get_tokenizer_name()
    except Exception:
        return "unknown"
