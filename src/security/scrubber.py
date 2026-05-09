# SPDX-License-Identifier: AGPL-3.0-or-later

"""Log scrubbing — redact credential patterns before emission."""

from __future__ import annotations

import logging
import re
import sys
import traceback
from types import TracebackType

_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"AIza[a-zA-Z0-9_-]{35}"),
    re.compile(r"gsk_[a-zA-Z0-9_-]{20,}"),
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


def install_scrub_excepthook() -> None:
    """Override sys.excepthook so unhandled-exception tracebacks are scrubbed.

    The root-logger ScrubFilter only catches messages that go through the
    logging module. An unhandled exception bypasses logging entirely — it
    flows through sys.excepthook → stderr, which can leak credentials from
    arg reprs or local-variable values quoted in tracebacks.
    """
    previous = sys.excepthook

    def _scrubbing_excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        sys.stderr.write(scrub(formatted))
        # Chain to the previous hook only if it's not the default — we've
        # already written to stderr, calling default would duplicate output.
        if previous is not sys.__excepthook__:
            previous(exc_type, exc_value, exc_tb)

    sys.excepthook = _scrubbing_excepthook
