"""System prompt extraction defense — canary tokens + fragment scanning."""

from __future__ import annotations

import hashlib


class PromptProtector:
    """Detects system prompt leakage in AI responses."""

    def __init__(self, system_prompt: str) -> None:
        self._canary = _make_canary(system_prompt)
        self._fragments = _extract_fragments(system_prompt)

    @property
    def canary(self) -> str:
        """The canary token for this prompt."""
        return self._canary

    def check_leakage(self, response: str) -> bool:
        """Return True if response contains prompt material."""
        if self._canary in response:
            return True
        return _contains_fragment(response, self._fragments)


def _make_canary(prompt: str) -> str:
    """Generate a deterministic canary token from prompt hash."""
    digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
    return f"CANARY_{digest}"


def _extract_fragments(prompt: str, min_words: int = 20) -> list[str]:
    """Extract fragments of 20+ words from the prompt."""
    sentences = prompt.replace("\n", ". ").split(".")
    return [s.strip().lower() for s in sentences if len(s.strip().split()) >= min_words]


def _contains_fragment(
    response: str,
    fragments: list[str],
) -> bool:
    """Check if response contains any prompt fragment."""
    lower = response.lower()
    return any(frag in lower for frag in fragments)
