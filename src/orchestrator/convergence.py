"""Convergence detection — embedding similarity with sliding window."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import numpy as np

from src.orchestrator.density import (
    compute_density,
    is_anomaly,
    update_baseline,
)
from src.repositories.log_repo import LogRepository

log = logging.getLogger(__name__)

DEFAULT_WINDOW = 5
DEFAULT_THRESHOLD = 0.75
DIVERGENCE_PROMPT = (
    "Identify the weakest assumption in the current direction "
    "and argue against it. If you genuinely cannot find a flaw, "
    "say so explicitly and explain why."
)


class ConvergenceDetector:
    """Detects conversation convergence via embedding similarity."""

    def __init__(
        self,
        log_repo: LogRepository,
        *,
        window_size: int = DEFAULT_WINDOW,
        threshold: float = DEFAULT_THRESHOLD,
        session_repo: object | None = None,
    ) -> None:
        self._log_repo = log_repo
        self._session_repo = session_repo
        self._window = window_size
        self._threshold = threshold
        self._model = None
        self._divergence_prompted = False

    def load_model(self) -> None:
        """Load the sentence-transformers model in SafeTensors format only.

        Per spec 004 FR-013 ("SafeTensors only — no pickle deserialization"),
        the loader passes use_safetensors=True to the underlying transformers
        from_pretrained call. If the model files don't include SafeTensors
        weights, the load fails hard rather than silently falling back to
        .bin (pickle), which would be a supply-chain attack surface.
        """
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                "all-MiniLM-L6-v2",
                model_kwargs={"use_safetensors": True},
            )
            log.info("Loaded embedding model (SafeTensors)")
        except Exception:
            log.warning("Failed to load embedding model — skipping")

    async def process_turn(
        self,
        *,
        turn_number: int,
        session_id: str,
        content: str,
    ) -> tuple[float, bool]:
        """Compute embedding, log, and return (similarity, should_inject_divergence).

        Skipped turns use turn_number <= 0 as a placeholder; similarity is
        still computed for cadence, but no logging and no divergence signal.
        The divergence flag is marked consumed here so callers cannot
        double-fire; they are responsible for actually enqueuing the prompt.
        """
        if self._model is None:
            return 0.0, False
        embedding = await _compute_embedding_async(self._model, content)
        similarity = await self._compute_similarity(session_id, embedding)
        if turn_number <= 0:
            return similarity, False
        diverge = self.should_diverge(similarity)
        await self._log_result(turn_number, session_id, embedding, similarity, diverge)
        await self._maybe_log_density(turn_number, session_id, content, embedding)
        if diverge:
            self.mark_divergence_prompted()
        return similarity, diverge

    async def _maybe_log_density(
        self,
        turn_number: int,
        session_id: str,
        content: str,
        embedding_bytes: bytes,
    ) -> None:
        """Compute density signal, log anomaly if any, update baseline.

        Spec 004 §FR-020: every turn computes a density score; anomalies
        (score > ratio × baseline_mean over the last 20 turns) get a
        `tier='density_anomaly'` row in convergence_log. Baseline grows
        every turn; the first ~20 turns produce no anomaly check.
        Skipped when no session_repo was wired (legacy callers).
        """
        if self._session_repo is None:
            return
        embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
        density = compute_density(content, embedding)
        baseline = await self._session_repo.get_density_baseline(session_id)
        if is_anomaly(density, baseline):
            mean = float(np.mean(baseline)) if baseline else 0.0
            await self._log_repo.log_density_anomaly(
                turn_number=turn_number,
                session_id=session_id,
                density_value=density,
                baseline_value=mean,
            )
        await self._session_repo.replace_density_baseline(
            session_id, update_baseline(baseline, density)
        )

    def is_converging(self, similarity: float) -> bool:
        """Check if similarity exceeds convergence threshold."""
        return similarity >= self._threshold

    def should_diverge(self, similarity: float) -> bool:
        """Check if divergence prompt should be injected."""
        if not self.is_converging(similarity):
            self._divergence_prompted = False
            return False
        return not self._divergence_prompted

    def should_escalate(self, similarity: float) -> bool:
        """Check if human escalation is needed."""
        return self.is_converging(similarity) and self._divergence_prompted

    def mark_divergence_prompted(self) -> None:
        """Record that a divergence prompt was injected."""
        self._divergence_prompted = True

    async def _compute_similarity(
        self,
        session_id: str,
        embedding: bytes,
    ) -> float:
        """Compute cosine similarity vs sliding window.

        Returns 0.0 until the window has at least 3 prior turns — with
        fewer, "similarity" just reflects short-text topicality rather
        than actual conversational convergence.
        """
        window = await self._log_repo.get_convergence_window(
            session_id,
            self._window,
        )
        if len(window) < 3:
            return 0.0
        return _cosine_similarity_window(embedding, window)

    async def _log_result(
        self,
        turn_number: int,
        session_id: str,
        embedding: bytes,
        similarity: float,
        divergence_prompted: bool = False,
    ) -> None:
        """Log convergence measurement."""
        await self._log_repo.log_convergence(
            turn_number=turn_number,
            session_id=session_id,
            embedding=embedding,
            similarity_score=similarity,
            divergence_prompted=divergence_prompted,
        )


async def _compute_embedding_async(
    model: object,
    text: str,
) -> bytes:
    """Run embedding computation in a thread (non-blocking)."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        partial(_encode_text, model, text),
    )
    return result


def _encode_text(model: object, text: str) -> bytes:
    """Encode text to embedding bytes."""
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tobytes()


def _cosine_similarity_window(
    current: bytes,
    window: list,
) -> float:
    """Average cosine similarity vs window embeddings."""
    current_vec = np.frombuffer(current, dtype=np.float32)
    similarities = []
    for entry in window:
        other = np.frombuffer(entry.embedding, dtype=np.float32)
        sim = _cosine_sim(current_vec, other)
        similarities.append(sim)
    return float(np.mean(similarities)) if similarities else 0.0


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    if a.shape != b.shape:
        return 0.0
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / norm) if norm > 0 else 0.0
