"""System prompt extraction defense — canary tokens + fragment scanning."""

from __future__ import annotations

import base64
import secrets


class PromptProtector:
    """Detects system prompt leakage in AI responses.

    Generates three random 16-char base32 canary tokens on construction.
    These are intended to be embedded in the system prompt via
    `prompts.tiers.assemble_prompt` (which generates its own canaries at
    assembly time). When detection is wired into the pipeline, construct
    a `PromptProtector` with the known canaries via `canaries=` kwarg.
    """

    def __init__(
        self,
        system_prompt: str,
        *,
        canaries: list[str] | None = None,
    ) -> None:
        self._canaries: list[str] = canaries if canaries is not None else _make_canaries()
        self._fragments = _extract_fragments(system_prompt)

    @property
    def canaries(self) -> list[str]:
        """The three canary tokens for this prompt."""
        return list(self._canaries)

    def check_leakage(self, response: str) -> bool:
        """Return True if response contains prompt material."""
        for canary in self._canaries:
            if canary in response:
                return True
        return _contains_fragment(response, self._fragments)


def _make_canaries() -> list[str]:
    """Generate three random 16-char base32 canary tokens."""
    return [base64.b32encode(secrets.token_bytes(10)).decode() for _ in range(3)]


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
