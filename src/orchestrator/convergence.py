"""Convergence detection — embedding similarity with sliding window."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import numpy as np

from src.repositories.log_repo import LogRepository

log = logging.getLogger(__name__)

DEFAULT_WINDOW = 5
DEFAULT_THRESHOLD = 0.85
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
    ) -> None:
        self._log_repo = log_repo
        self._window = window_size
        self._threshold = threshold
        self._model = None
        self._divergence_prompted = False

    def load_model(self) -> None:
        """Load the sentence-transformers model (SafeTensors)."""
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                "all-MiniLM-L6-v2",
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
    ) -> float:
        """Compute embedding and check convergence. Non-blocking.

        Skipped turns use turn_number <= 0 as a placeholder; we still compute
        similarity for cadence decisions but skip logging to avoid PK collisions.
        """
        if self._model is None:
            return 0.0
        embedding = await _compute_embedding_async(self._model, content)
        similarity = await self._compute_similarity(session_id, embedding)
        if turn_number > 0:
            await self._log_result(
                turn_number,
                session_id,
                embedding,
                similarity,
            )
        return similarity

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
    ) -> None:
        """Log convergence measurement."""
        await self._log_repo.log_convergence(
            turn_number=turn_number,
            session_id=session_id,
            embedding=embedding,
            similarity_score=similarity,
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
