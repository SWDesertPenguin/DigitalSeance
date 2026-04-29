"""Exfiltration filtering — strip data leakage vectors."""

from __future__ import annotations

import re

_MARKDOWN_IMAGES = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_HTML_SRC = re.compile(r'<[^>]+\bsrc\s*=\s*["\'][^"\']+["\'][^>]*>', re.IGNORECASE)
_DATA_URLS = re.compile(
    r"https?://[^\s]+[?&](?:data|token|secret|key|password)=",
    re.IGNORECASE,
)
_API_KEYS = re.compile(r"sk-[a-zA-Z0-9_-]{20,}")
_ANTHROPIC_KEYS = re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}")
_GEMINI_KEYS = re.compile(r"AIza[a-zA-Z0-9_-]{35}")
_GROQ_KEYS = re.compile(r"gsk_[a-zA-Z0-9_-]{20,}")
_JWT_TOKENS = re.compile(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+")
_FERNET_TOKENS = re.compile(r"gAAAAA[a-zA-Z0-9_-]{40,}")

_CREDENTIAL_PATTERNS = [
    _API_KEYS,
    _ANTHROPIC_KEYS,
    _GEMINI_KEYS,
    _GROQ_KEYS,
    _JWT_TOKENS,
    _FERNET_TOKENS,
]

# Documented placeholder shapes that are obviously not real credentials.
# Exempt these from redaction so code-review / docs discussions remain readable.
# Real credentials are random ASCII; they don't contain "example", "test",
# "fake", "XXX", or "your-key" tokens.
_CRED_PLACEHOLDER = re.compile(
    r"(?:sk-ant-|sk-|gsk_|AIza|eyJ)"
    r"(?:"
    r"\.{3,}[A-Za-z0-9_-]*"
    r"|X{3,}[A-Za-z0-9_-]*"
    r"|(?:example|test|fake|dummy|placeholder|sample)[A-Za-z0-9_-]*"
    r"|your[_-]?key[A-Za-z0-9_-]*"
    r")",
    re.IGNORECASE,
)

# Context assembly markers that must not leak into stored messages
_SPOTLIGHT_MARKER = re.compile(r"\^[0-9a-f_]{5,8}\^")
_SACP_TAGS = re.compile(r"</?sacp:(?:human|ai)>|@sacp:(?:human|ai)\b")
# Legacy bracket-format canaries from pre-hardening deployments.
# New-format canaries (random base32, no structural wrapper) are detected
# by PromptProtector.check_leakage rather than stripped by regex.
_CANARY_LEGACY = re.compile(r"\[Internal:\s*CANARY_[0-9a-f]+\]")


def filter_exfiltration(text: str) -> tuple[str, list[str]]:
    """Strip exfiltration patterns. Returns (cleaned, flags)."""
    flags: list[str] = []
    result = text
    result = _strip_images(result, flags)
    result = _strip_html_src(result, flags)
    result = _flag_data_urls(result, flags)
    result = _redact_credentials(result, flags)
    result = _strip_context_markers(result, flags)
    return result, flags


def _strip_images(text: str, flags: list[str]) -> str:
    """Remove markdown image syntax."""
    if _MARKDOWN_IMAGES.search(text):
        flags.append("markdown_image_stripped")
    return _MARKDOWN_IMAGES.sub("[image removed]", text)


def _strip_html_src(text: str, flags: list[str]) -> str:
    """Remove HTML elements with src attributes."""
    if _HTML_SRC.search(text):
        flags.append("html_src_stripped")
    return _HTML_SRC.sub("[element removed]", text)


def _flag_data_urls(text: str, flags: list[str]) -> str:
    """Flag URLs with data-embedding parameters."""
    if _DATA_URLS.search(text):
        flags.append("data_url_detected")
    return text


def _redact_credentials(text: str, flags: list[str]) -> str:
    """Replace credential patterns with [REDACTED]; preserve documented placeholders."""
    placeholders: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"\x00CRED_PH_{len(placeholders) - 1}\x00"

    masked = _CRED_PLACEHOLDER.sub(_stash, text)
    redacted = False
    for pattern in _CREDENTIAL_PATTERNS:
        if pattern.search(masked):
            redacted = True
            masked = pattern.sub("[REDACTED]", masked)
    if redacted:
        flags.append("credential_redacted")
    for i, original in enumerate(placeholders):
        masked = masked.replace(f"\x00CRED_PH_{i}\x00", original)
    return masked


def _strip_context_markers(text: str, flags: list[str]) -> str:
    """Remove spotlighting markers, SACP tags, and canary tokens."""
    result = text
    if _SPOTLIGHT_MARKER.search(result):
        flags.append("spotlight_marker_stripped")
        result = _SPOTLIGHT_MARKER.sub("", result)
    if _SACP_TAGS.search(result):
        flags.append("sacp_tag_stripped")
        result = _SACP_TAGS.sub("", result)
    if _CANARY_LEGACY.search(result):
        flags.append("canary_token_stripped")
        result = _CANARY_LEGACY.sub("", result)
    return result
