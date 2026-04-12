"""Inter-agent spotlighting — datamark AI responses."""

from __future__ import annotations

import hashlib


def spotlight(content: str, source_id: str) -> str:
    """Apply word-level datamarking to disrupt injection."""
    marker = _make_marker(source_id)
    words = content.split()
    return " ".join(f"{marker}{w}" for w in words)


def _make_marker(source_id: str) -> str:
    """Generate a short hash-based marker for the source."""
    digest = hashlib.sha256(source_id.encode()).hexdigest()[:6]
    return f"^{digest}^"


def should_spotlight(speaker_type: str) -> bool:
    """Only AI responses should be spotlighted."""
    return speaker_type == "ai"
