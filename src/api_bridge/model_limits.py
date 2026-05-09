"""Authoritative max-input-token catalog for known provider models.

Defense-in-depth for context assembly: the participant's declared
`context_window` is operator-supplied and may be wrong (gpt-3.5-turbo
registered at 128K vs the actual 16,385). Without a clamp the budget
calculator allocates the declared window, and dispatch overshoots the
provider limit. This module provides a small lookup so the assembler
can floor the budget at the model's true limit.

Resolution order:
  1. The LiteLLM adapter package's `litellm_max_input_tokens(model)` —
     covers every model LiteLLM ships metadata for (the bulk of the
     catalog). Lazy-imported so the FR-005 architectural test continues
     to pass: this module itself does not import `litellm`.
  2. A small explicit fallback table — covers the handful of models the
     project tests against most often, so a LiteLLM metadata regression
     doesn't take this defense down with it.
  3. None — unknown model. Caller trusts the operator-declared value.

The fallback table is deliberately minimal; expanding it indefinitely
turns this module into a maintenance burden. Add an entry only when a
production-relevant model is missing from LiteLLM metadata.

Spec 020 / T076 relocates the inline `import litellm` that previously
lived in `_from_litellm()` to `src/api_bridge/litellm/capabilities.py`
so the FR-005 architectural test passes for this file.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Last-resort fallback for the models the project exercises most heavily.
# Numbers track each provider's published context window as of 2026-05.
_FALLBACK_MAX_INPUT_TOKENS: dict[str, int] = {
    "gpt-3.5-turbo": 16_385,
    "gpt-4": 8_192,
    "gpt-4-turbo": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "claude-3-5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-flash-lite": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
}


def known_max_input_tokens(model: str) -> int | None:
    """Authoritative max input tokens for `model`, or None if unknown.

    Returns the smallest of the LiteLLM metadata value and the explicit
    fallback table when both are present, so a metadata bug that
    inflates a window doesn't override a hand-pinned floor.
    """
    bare = _strip_provider_prefix(model)
    litellm_value = _from_litellm(model)
    fallback_value = _FALLBACK_MAX_INPUT_TOKENS.get(bare)
    if litellm_value is not None and fallback_value is not None:
        return min(litellm_value, fallback_value)
    return litellm_value if litellm_value is not None else fallback_value


def _from_litellm(model: str) -> int | None:
    """Pull max_input_tokens via the LiteLLM adapter package helper.

    Lazy-imports `src.api_bridge.litellm.capabilities` so this module
    holds no top-level dependency on the LiteLLM adapter package — keeps
    `model_limits.py` callable from contexts where the adapter package
    is absent (e.g., topology 7) without breaking the FR-005
    architectural test.
    """
    try:
        from src.api_bridge.litellm.capabilities import litellm_max_input_tokens
    except ImportError:
        return None
    try:
        return litellm_max_input_tokens(model)
    except Exception:
        return None


def _strip_provider_prefix(model: str) -> str:
    """Remove the LiteLLM provider prefix so fallback lookups match.

    `anthropic/claude-sonnet-4-6` -> `claude-sonnet-4-6`,
    `gemini/gemini-2.5-flash-lite` -> `gemini-2.5-flash-lite`, etc.
    """
    for prefix in ("anthropic/", "openai/", "gemini/", "vertex_ai/", "google/"):
        if model.startswith(prefix):
            return model[len(prefix) :]
    return model
