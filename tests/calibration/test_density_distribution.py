"""Calibration: density distribution across benign + adversarial corpora.

Phase 1 ships the 1.5× default threshold (spec 004 §FR-020). This test
emits a histogram artifact (`tests/calibration/density_distribution.json`)
that Phase 3 retuning consumes — the assertion is only that the artifact
is generated, NOT that specific values fall in specific ranges. The
artifact carries the per-corpus density distribution observed against
the existing red-team / benign fixtures so calibration decisions are
data-driven rather than guess-based.

Skipped automatically if the embedding model cannot load (offline CI,
missing model cache).
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

from src.orchestrator.density import compute_density_from_text

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACT_PATH = REPO_ROOT / "tests" / "calibration" / "density_distribution.json"


def _load_corpus(path: Path) -> list[str]:
    """Read a corpus file, dropping comments and blank lines."""
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def _try_load_model():
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(
            "all-MiniLM-L6-v2",
            model_kwargs={"use_safetensors": True},
        )
    except Exception:
        return None


def _bucket(value: float) -> str:
    """Coarse density bucket for histogram emission."""
    if value < 1.0:
        return "lt_1"
    if value < 2.0:
        return "1_to_2"
    if value < 3.0:
        return "2_to_3"
    if value < 5.0:
        return "3_to_5"
    return "ge_5"


def _summarize(densities: list[float]) -> dict[str, object]:
    """Per-corpus stats: count, mean, median, p95, max, histogram."""
    if not densities:
        return {"n": 0}
    sorted_d = sorted(densities)
    p95_idx = max(0, int(len(sorted_d) * 0.95) - 1)
    histogram: dict[str, int] = {}
    for d in densities:
        key = _bucket(d)
        histogram[key] = histogram.get(key, 0) + 1
    return {
        "n": len(densities),
        "mean": round(statistics.fmean(densities), 4),
        "median": round(statistics.median(densities), 4),
        "p95": round(sorted_d[p95_idx], 4),
        "max": round(max(densities), 4),
        "histogram": histogram,
    }


def test_emit_density_distribution_artifact():
    model = _try_load_model()
    if model is None:
        pytest.skip("embedding model unavailable — skipping calibration emit")
    fixtures = REPO_ROOT / "tests" / "fixtures"
    corpora = {
        "benign": _load_corpus(fixtures / "benign_corpus.txt"),
        "adversarial": _load_corpus(fixtures / "adversarial_corpus.txt"),
    }
    artifact: dict[str, object] = {}
    for name, lines in corpora.items():
        densities = [compute_density_from_text(line, model) for line in lines]
        densities = [d for d in densities if d > 0]
        artifact[name] = _summarize(densities)
    artifact["threshold_default"] = 1.5
    artifact["window_size"] = 20
    # Trailing newline matches the end-of-file-fixer pre-commit hook so
    # the committed artifact doesn't oscillate every time the test runs.
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    assert ARTIFACT_PATH.exists()
    payload = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    # Sanity: both corpora produced data
    assert payload["benign"]["n"] > 0
    assert payload["adversarial"]["n"] > 0
