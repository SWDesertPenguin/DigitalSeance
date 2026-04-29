"""Context sanitization - strip injection patterns from messages."""

from __future__ import annotations

import re
import unicodedata

# Cyrillic + Greek letters commonly used as Latin homoglyphs in injection
# payloads. Round02 surfaced an attack where Cyrillic 'a' (U+0430) replaced
# Latin 'a' (U+0061), defeating regex matches that assumed ASCII. Folding
# only applies to mixed-script words (those that contain BOTH Latin and
# Cyrillic/Greek), so legitimate Russian / Greek text stays readable.
#
# Codepoints are built from chr() calls to keep this source file pure ASCII;
# avoids encoding mismatches with tools that read .py files using the
# system default codec on Windows (cp1252).
_CONFUSABLE_PAIRS = [
    # Cyrillic lowercase -> Latin
    (0x0430, "a"),  # CYRILLIC SMALL LETTER A
    (0x0435, "e"),  # CYRILLIC SMALL LETTER IE
    (0x043E, "o"),  # CYRILLIC SMALL LETTER O
    (0x0440, "p"),  # CYRILLIC SMALL LETTER ER
    (0x0441, "c"),  # CYRILLIC SMALL LETTER ES
    (0x0443, "y"),  # CYRILLIC SMALL LETTER U
    (0x0445, "x"),  # CYRILLIC SMALL LETTER HA
    (0x0456, "i"),  # CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I
    (0x0458, "j"),  # CYRILLIC SMALL LETTER JE
    (0x0455, "s"),  # CYRILLIC SMALL LETTER DZE
    # Cyrillic uppercase -> Latin
    (0x0410, "A"),
    (0x0415, "E"),
    (0x041E, "O"),
    (0x0420, "P"),
    (0x0421, "C"),
    (0x0423, "Y"),
    (0x0425, "X"),
    (0x0406, "I"),
    (0x0408, "J"),
    (0x0405, "S"),
    # Greek lowercase
    (0x03BD, "v"),  # GREEK SMALL LETTER NU
    (0x03BF, "o"),  # GREEK SMALL LETTER OMICRON
    (0x03C1, "p"),  # GREEK SMALL LETTER RHO
    # Greek uppercase
    (0x039F, "O"),
    (0x03A1, "P"),
]
_CONFUSABLES = str.maketrans({chr(cp): latin for cp, latin in _CONFUSABLE_PAIRS})

# Match words that contain BOTH a Latin letter and a Cyrillic/Greek letter.
# Pure-script words (all Latin or all Cyrillic) don't match and pass through.
# Greek block: U+0370-U+03FF. Cyrillic block: U+0400-U+04FF. Range built
# from chr() calls so this source file stays pure ASCII.
_NON_LATIN_RANGE = "[" + chr(0x0370) + "-" + chr(0x03FF) + chr(0x0400) + "-" + chr(0x04FF) + "]"
_MIXED_SCRIPT_WORD = re.compile(
    r"\b\w*(?:"
    r"[A-Za-z]\w*" + _NON_LATIN_RANGE + r"|" + _NON_LATIN_RANGE + r"\w*[A-Za-z]" + r")\w*\b"
)


def _fold_homoglyphs(text: str) -> str:
    """Fold homoglyphs to Latin in mixed-script words only."""
    return _MIXED_SCRIPT_WORD.sub(
        lambda m: m.group(0).translate(_CONFUSABLES),
        text,
    )


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
    "["
    + chr(0x200B)
    + "-"
    + chr(0x200F)
    + chr(0x2028)
    + "-"
    + chr(0x202F)
    + chr(0xFEFF)
    + chr(0x00AD)
    + "]"
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
    """Strip all known injection patterns from text.

    Applies NFKC normalization (collapses full-width / compatibility forms)
    and a mixed-script homoglyph fold (Cyrillic/Greek lookalikes -> Latin in
    words that mix scripts) BEFORE pattern matching, so injection attempts
    that obfuscate ASCII via Unicode tricks still hit the existing regexes.
    """
    normalized = unicodedata.normalize("NFKC", text)
    folded = _fold_homoglyphs(normalized)
    result = folded
    for pattern in _ALL_PATTERNS:
        result = pattern.sub("", result)
    return _collapse_whitespace(result)


def _collapse_whitespace(text: str) -> str:
    """Collapse multiple spaces into one, strip edges."""
    return re.sub(r"  +", " ", text).strip()
