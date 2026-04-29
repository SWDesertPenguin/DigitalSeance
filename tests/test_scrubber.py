"""US7: Log scrubbing tests."""

from __future__ import annotations

import io
import sys

from src.security.scrubber import install_scrub_excepthook, scrub


def test_api_key_redacted() -> None:
    """OpenAI-style API key is redacted."""
    text = "Error with key sk-abc123456789012345678901"
    result = scrub(text)
    assert "sk-abc" not in result
    assert "[REDACTED]" in result


def test_anthropic_key_redacted() -> None:
    """Anthropic API key is redacted."""
    text = "Using sk-ant-api03-abcdefghijklmnopqrstuv"
    result = scrub(text)
    assert "sk-ant" not in result
    assert "[REDACTED]" in result


def test_jwt_redacted() -> None:
    """JWT token is redacted."""
    text = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"  # gitleaks:allow
    result = scrub(text)
    assert "eyJ" not in result
    assert "[REDACTED]" in result


def test_fernet_token_redacted() -> None:
    """Fernet encryption token is redacted."""
    text = "Key: gAAAAABk" + "a" * 40
    result = scrub(text)
    assert "gAAAAA" not in result


def test_clean_text_unchanged() -> None:
    """Normal text without credentials passes through."""
    text = "Connection to database successful on port 5432"
    assert scrub(text) == text


def test_key_value_redacted() -> None:
    """Generic key=value patterns are redacted."""
    text = "Config api_key=mysecretvalue123"
    result = scrub(text)
    assert "mysecretvalue" not in result


def test_gemini_key_redacted() -> None:
    """Gemini API key (AIza prefix, 39 chars total) is redacted."""
    text = "Error with key AIzaSyA-bcdefghijklmnopqrstuvwxyz0123456"  # gitleaks:allow
    result = scrub(text)
    assert "AIza" not in result
    assert "[REDACTED]" in result


def test_groq_key_redacted() -> None:
    """Groq API key (gsk_ prefix) is redacted."""
    text = "Error with key gsk_abcdefghijklmnopqrstuv1234567890"  # gitleaks:allow
    result = scrub(text)
    assert "gsk_" not in result
    assert "[REDACTED]" in result


def test_excepthook_scrubs_traceback(monkeypatch) -> None:
    """install_scrub_excepthook redacts credentials in unhandled-exception output."""
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured)
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    install_scrub_excepthook()
    try:
        raise RuntimeError("leaked sk-ant-api03-abcdefghijklmnopqrstuv in args")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    output = captured.getvalue()
    assert "sk-ant" not in output
    assert "[REDACTED]" in output
    assert "RuntimeError" in output
