# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pure-function detectors for AI output signals — questions + exit intent.

These signals surface in the Web UI so facilitators can see when an AI
asks a question that gets buried under subsequent turns, or when an AI
voluntarily steps back but the loop keeps dispatching to it. Both
patterns were observed in Test06-Web07 (Haiku repeatedly asking humans
direct questions; Haiku saying "I'm stepping back" 5 times across 30
turns while the orchestrator kept routing turns its way).
"""

from __future__ import annotations

import re

# Phrases that strongly indicate an AI is voluntarily stepping back.
# Conservative list — false positives would auto-flip a healthy AI to
# observer and silence it. The matched phrase is surfaced verbatim to
# the facilitator so they can sanity-check before honoring the request.
_EXIT_PHRASES = (
    r"\bi(?:'m|\s+am)\s+stepping\s+back\b",
    r"\bi(?:'m|\s+am)\s+(?:not|done)\s+responding(?:\s+further)?\b",
    r"\bi(?:'m|\s+am)\s+bowing\s+out\b",
    r"\bthis\s+conversation\s+is\s+over\b",
    r"\bi(?:'ll|\s+will)\s+(?:stop|step\s+away)\b",
    r"\bi(?:'m|\s+am)\s+going\s+silent\b",
)
_EXIT_RE = re.compile("|".join(_EXIT_PHRASES), re.IGNORECASE)


def detect_exit_intent(content: str) -> str | None:
    """Return the matched phrase if AI signals voluntary exit, else None."""
    if not content:
        return None
    m = _EXIT_RE.search(content)
    return m.group(0) if m else None


_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+")


def extract_questions(
    content: str,
    roster: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    """Return questions in `content` directed at a human participant.

    Heuristic: a sentence with `?` that names a human participant
    (provider == "human") by display name. AI-to-AI questions are
    excluded — the loop will route the response to the named AI
    naturally; only questions that risk being missed by a human need
    surfacing in the panel.

    Why: the original second-person trigger ("you/your") caused every
    AI turn in a multi-AI session to fire the event (models routinely
    end responses with "What do you think?"), flooding the panel and
    making it unusable. Restricting to named humans eliminates the
    false-positive class while preserving the original Test06-Web07
    use case: Haiku says "Alice, could you clarify?" → fires once.
    """
    if not content or "?" not in content:
        return []
    human_names = _human_names_lower(roster or {})
    if not human_names:
        return []
    out: list[str] = []
    for sentence in _SENTENCE_RE.findall(content):
        if "?" not in sentence:
            continue
        clean = sentence.strip()
        if clean and _addresses_someone(clean, human_names):
            out.append(clean)
    return out


def _human_names_lower(roster: dict[str, dict[str, str]]) -> set[str]:
    """Lowercased display names of human participants only (provider == "human")."""
    return {
        (p.get("display_name") or "").strip().lower()
        for p in roster.values()
        if p.get("provider") == "human"
    } - {""}


def _addresses_someone(sentence: str, names: set[str]) -> bool:
    """True iff a name from the given set appears anywhere in the sentence."""
    s = sentence.lower()
    return any(name and name in s for name in names)
