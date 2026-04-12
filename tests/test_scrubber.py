"""US7: Log scrubbing tests."""

from __future__ import annotations

from src.security.scrubber import scrub


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
