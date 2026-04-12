"""Context sanitization — strip injection patterns from messages."""

from __future__ import annotations

import re

_CHATML_TOKENS = re.compile(
    r"<\|(?:im_start|im_end|system|user|assistant)\|>",
)
_ROLE_MARKERS = re.compile(
    r"(?:^|\n)\s*(?:system|assistant|user)\s*:",
    re.IGNORECASE,
)
_LLAMA_MARKERS = re.compile(r"\[/?INST\]")
_HTML_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
_OVERRIDE_PHRASES = re.compile(
    r"(?:ignore|disregard|forget)"
    r" (?:all |the )?(?:previous|above|prior)"
    r"(?: instructions| rules| guidelines)?",
    re.IGNORECASE,
)
_NEW_INSTRUCTIONS = re.compile(
    r"(?:new|updated|revised)" r" (?:instruction|rule|directive)s?\s*:",
    re.IGNORECASE,
)
_FROM_NOW_ON = re.compile(r"from now on", re.IGNORECASE)
_INVISIBLE_UNICODE = re.compile(
    r"[\u200b-\u200f\u2028-\u202f\ufeff\u00ad]",
)

_ALL_PATTERNS = [
    _CHATML_TOKENS,
    _ROLE_MARKERS,
    _LLAMA_MARKERS,
    _HTML_COMMENTS,
    _OVERRIDE_PHRASES,
    _NEW_INSTRUCTIONS,
    _FROM_NOW_ON,
    _INVISIBLE_UNICODE,
]


def sanitize(text: str) -> str:
    """Strip all known injection patterns from text."""
    result = text
    for pattern in _ALL_PATTERNS:
        result = pattern.sub("", result)
    return _collapse_whitespace(result)


def _collapse_whitespace(text: str) -> str:
    """Collapse multiple spaces into one, strip edges."""
    return re.sub(r"  +", " ", text).strip()
