"""Log scrubbing — redact credential patterns before emission."""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+"),
    re.compile(r"gAAAAA[a-zA-Z0-9_-]{40,}"),
    re.compile(r"(?:api[_-]?key|token|secret)\s*[=:]\s*\S+", re.IGNORECASE),
]

REDACTED = "[REDACTED]"


def scrub(text: str) -> str:
    """Redact all credential patterns from text."""
    result = text
    for pattern in _PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


class ScrubFilter(logging.Filter):
    """Logging filter that scrubs credentials from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Scrub the log message and return True (always emit)."""
        if isinstance(record.msg, str):
            record.msg = scrub(record.msg)
        return True


def install_scrub_filter() -> None:
    """Install the scrub filter on the root logger."""
    root = logging.getLogger()
    root.addFilter(ScrubFilter())
