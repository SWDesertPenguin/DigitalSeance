# SPDX-License-Identifier: AGPL-3.0-or-later

"""Token counting for the LiteLLM adapter per spec 020 FR-012.

Uses the per-model tokenizer adapters in `src/api_bridge/tokenizer.py`.
Returns a conservative-overestimate token count using the default
estimator when the model is unknown, with an audit-log entry per FR-012.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.api_bridge.tokenizer import default_estimator, get_tokenizer_for_model

log = logging.getLogger(__name__)

# Conservative overestimate multiplier for unknown-model paths. Cost
# tracking will be slightly inflated for unknown models — the safe
# direction per FR-012.
_UNKNOWN_OVERESTIMATE_FACTOR = 1.10


def count_tokens(messages: list[dict[str, Any]], model: str) -> int:
    """Count inbound tokens for `messages` using the participant's model tokenizer.

    Falls back to the default estimator with a conservative overestimate
    when the model is unknown; emits an audit-log entry on the
    unknown-model path per FR-012.
    """
    text = _flatten_messages(messages)
    try:
        adapter = get_tokenizer_for_model(model)
    except Exception:
        log.warning(
            "audit: unknown-tokenizer fallback for model=%s; "
            "using default estimator with conservative overestimate",
            model,
        )
        raw = default_estimator().count_tokens(text)
        return int(raw * _UNKNOWN_OVERESTIMATE_FACTOR)
    try:
        return adapter.count_tokens(text)
    except Exception:
        log.warning(
            "audit: tokenizer adapter for %s raised; falling back to default estimator",
            model,
        )
        raw = default_estimator().count_tokens(text)
        return int(raw * _UNKNOWN_OVERESTIMATE_FACTOR)


def _flatten_messages(messages: list[dict[str, Any]]) -> str:
    """Render a message list as text for tokenizer input.

    The exact serialization is not load-bearing for SACP — what matters
    is determinism and that role + content are both counted. Tokenizer
    drift across providers means counts are inherently advisory; the
    flatten step keeps the count stable across calls with the same input.
    """
    parts: list[str] = []
    for msg in messages:
        role = str(msg.get("role", ""))
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"{role}: {content}")
        else:
            parts.append(f"{role}: {json.dumps(content, sort_keys=True)}")
    return "\n".join(parts)
