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
_SECOND_PERSON_RE = re.compile(r"\b(?:you|your|yours|y'all)\b", re.IGNORECASE)


def extract_questions(
    content: str,
    roster: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    """Return the open questions in `content` plausibly aimed at a participant.

    Heuristic: a sentence with a `?` that EITHER names a participant
    (any role — human or AI) OR uses a second-person pronoun. Captures
    the Test06-Web07 pattern where Haiku asked direct questions that
    scrolled away because no peer recognized the address. Rhetorical
    questions ("Why does this happen? Because...") rarely match either
    criterion, so they're filtered out cheaply.
    """
    if not content or "?" not in content:
        return []
    names = _participant_names_lower(roster or {})
    out: list[str] = []
    for sentence in _SENTENCE_RE.findall(content):
        if "?" not in sentence:
            continue
        clean = sentence.strip()
        if not clean:
            continue
        if _addresses_someone(clean, names) or _SECOND_PERSON_RE.search(clean):
            out.append(clean)
    return out


def _participant_names_lower(roster: dict[str, dict[str, str]]) -> set[str]:
    """Lowercased display names of all participants in the roster."""
    return {(p.get("display_name") or "").strip().lower() for p in roster.values()} - {""}


def _addresses_someone(sentence: str, names: set[str]) -> bool:
    """True iff a roster display_name appears anywhere in the sentence."""
    s = sentence.lower()
    return any(name and name in s for name in names)
