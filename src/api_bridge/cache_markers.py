# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 FR-003 cache_hit / cache_miss routing_log emission helper.

The dispatch path calls ``emit_cache_marker(...)`` after every successful
adapter dispatch. When the adapter populated
``ProviderResponse.cached_prefix_tokens`` from the provider's usage
payload (Anthropic ``cache_read_input_tokens`` or OpenAI
``prompt_tokens_details.cached_tokens``), we append a routing_log row
with ``reason='cache_hit'`` (positive token count) or ``'cache_miss'``
(zero). When the adapter reports ``None`` we stay silent — the
provider does not surface cache visibility on that leg, so emitting a
synthetic marker would lie about observability.

This module is deliberately tiny and stays out of the orchestrator
module graph so unit tests can import it without pulling
``src.orchestrator.loop`` and its transitive imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.api_bridge.adapter import ProviderResponse
    from src.repositories.log_repo import LogRepository


async def emit_cache_marker(
    log_repo: LogRepository,
    session_id: str,
    turn_number: int,
    speaker: object,
    response: ProviderResponse,
) -> None:
    """Append a cache_hit / cache_miss routing_log row when the adapter signalled.

    Silent no-op when ``response.cached_prefix_tokens`` is None. The
    marker row is separate from the per-turn routing-decision row so
    spec 022 / 016 readers can group by ``reason`` without parsing the
    primary decision payload.
    """
    tokens = response.cached_prefix_tokens
    if tokens is None:
        return
    reason = "cache_hit" if tokens > 0 else "cache_miss"
    await log_repo.log_routing(
        session_id=session_id,
        turn_number=turn_number,
        intended=speaker.id,
        actual=speaker.id,
        action="cache_event",
        complexity="n/a",
        domain_match=False,
        reason=reason,
    )
