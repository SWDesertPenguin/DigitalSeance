# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLMLingua2mBERTCompressor — Phase 2 hard-compression per spec 026 FR-008.

Phase 2 master switch is ``SACP_COMPRESSION_PHASE2_ENABLED``. When
false (default), this compressor raises ``NotImplementedError`` naming
the env var; the CompressorService catches and falls through per FR-020.

When the env var is true:

  * If the ``llmlingua`` package is installed (optional dependency
    landed via the ``compression-phase2`` extra in ``pyproject.toml``),
    the compressor loads the LLMLingua-2 mBERT model on first
    ``compress(...)`` call (per-process singleton) and runs the
    ``compress_prompt(...)`` API against the payload.
  * If the dependency is NOT installed, the compressor raises
    ``NotImplementedError`` pointing at the install command. The
    CompressorService still catches and falls through; operators see
    the routing_log marker `compression_pipeline_error` and know to
    install the extra to engage Layer 4.

Output is wrapped in the XML boundary marker (FR-012) with MIN-tier
inheritance (FR-011); the CompressorService records per-call timing
in ``compression_log.duration_ms`` (V14 budget).

Model load is gated to lazy first-call to avoid paying the import-time
cost on every orchestrator startup. The model lives in a module-level
slot; subsequent calls reuse it. Per-process singleton matches the
spec 020 ``AdapterRegistry`` lifecycle pattern.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from src.compression.markers import wrap as wrap_boundary_marker
from src.compression.segments import CompressedSegment
from src.compression.trust_tier import refuse_tier_one

_MODEL_LOCK = threading.Lock()
_PROMPT_COMPRESSOR: Any = None

# LLMLingua-2 mBERT Hugging Face checkpoint per research.md §8. Override
# via env var so operators on air-gapped stacks can point at a mirror or
# a local SafeTensors-only weights bundle.
_DEFAULT_MODEL = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"


class LLMLingua2mBERTCompressor:
    """Phase 2 hard-compression default. Real body lands when the dep is installed."""

    COMPRESSOR_ID: str = "llmlingua2_mbert"
    # Real-path version bumps from "0-scaffold" to "1-llmlingua-real" so the
    # compression_log + cache-key (FR-004) reflect the active body.
    COMPRESSOR_VERSION: str = "1-llmlingua-real"

    def compress(
        self,
        payload: str,
        target_budget: int,
        trust_tier: str,
    ) -> CompressedSegment:
        refuse_tier_one(trust_tier)
        _require_phase2_enabled()
        compressor = _load_prompt_compressor()
        compressed_text, output_tokens = _run_compress_prompt(compressor, payload, target_budget)
        marker = wrap_boundary_marker(
            "",
            source_tier=trust_tier,
            compressor_id=self.COMPRESSOR_ID,
            compressor_version=self.COMPRESSOR_VERSION,
        )
        return CompressedSegment(
            output_text=wrap_boundary_marker(
                compressed_text,
                source_tier=trust_tier,
                compressor_id=self.COMPRESSOR_ID,
                compressor_version=self.COMPRESSOR_VERSION,
            ),
            output_tokens=output_tokens,
            trust_tier=trust_tier,
            boundary_marker=marker,
            compressor_id=self.COMPRESSOR_ID,
            compressor_version=self.COMPRESSOR_VERSION,
        )


def _require_phase2_enabled() -> None:
    if os.environ.get("SACP_COMPRESSION_PHASE2_ENABLED") != "true":
        raise NotImplementedError(
            "Phase 2 not enabled; set SACP_COMPRESSION_PHASE2_ENABLED=true to opt in"
        )


def _load_prompt_compressor() -> Any:
    """Lazy-load and cache the LLMLingua-2 mBERT model.

    Raises ``NotImplementedError`` when the optional ``llmlingua``
    dependency is not installed (operator opted into Phase 2 without
    landing the install). The CompressorService catches and falls
    through to un-compressed payload per FR-020.
    """
    global _PROMPT_COMPRESSOR
    if _PROMPT_COMPRESSOR is not None:
        return _PROMPT_COMPRESSOR
    with _MODEL_LOCK:
        if _PROMPT_COMPRESSOR is not None:
            return _PROMPT_COMPRESSOR
        try:
            from llmlingua import PromptCompressor
        except ImportError as exc:
            raise NotImplementedError(
                "llmlingua dependency not installed; install the "
                "compression-phase2 extra: uv pip install -e .[compression-phase2]"
            ) from exc
        model_name = os.environ.get("SACP_LLMLINGUA_MODEL", _DEFAULT_MODEL)
        _PROMPT_COMPRESSOR = PromptCompressor(
            model_name=model_name,
            use_llmlingua2=True,
        )
        return _PROMPT_COMPRESSOR


def _run_compress_prompt(
    compressor: Any,
    payload: str,
    target_budget: int,
) -> tuple[str, int]:
    """Invoke the LLMLingua-2 compressor and return (text, output_token_count).

    The library's ``compress_prompt`` API accepts either a ``rate`` (0..1
    target compression ratio) or a ``target_token`` count. We pass the
    spec 026 ``target_budget`` directly; the library caps to its internal
    minimum if the budget is below the structural overhead floor.
    """
    result = compressor.compress_prompt(
        context=[payload],
        target_token=max(target_budget, 1),
        use_sentence_level_filter=False,
        use_token_level_filter=True,
    )
    compressed_text = str(result.get("compressed_prompt", ""))
    output_tokens = int(result.get("compressed_tokens", len(compressed_text.split())))
    return compressed_text, output_tokens


def _reset_model_for_tests() -> None:
    """Drop the cached model so a fresh load can fire. Test-only hook."""
    global _PROMPT_COMPRESSOR
    _PROMPT_COMPRESSOR = None
