"""US2: Inter-agent spotlighting tests."""

from __future__ import annotations

from src.security.spotlighting import should_spotlight, spotlight


def test_datamarks_inserted() -> None:
    """Spotlight inserts markers between words."""
    result = spotlight("hello world", "agent-a")
    assert "^" in result
    assert "hello" in result
    assert "world" in result


def test_marker_contains_source_hash() -> None:
    """Marker is derived from source ID."""
    result = spotlight("test", "agent-a")
    # Should have hash-based prefix
    parts = result.split("^")
    assert len(parts) >= 3  # ^hash^word


def test_different_sources_different_markers() -> None:
    """Different source IDs produce different markers."""
    r1 = spotlight("test", "agent-a")
    r2 = spotlight("test", "agent-b")
    assert r1 != r2


def test_ai_messages_should_spotlight() -> None:
    """AI speaker type should be spotlighted."""
    assert should_spotlight("ai") is True


def test_human_messages_not_spotlighted() -> None:
    """Human messages are NOT spotlighted."""
    assert should_spotlight("human") is False


def test_system_messages_not_spotlighted() -> None:
    """System messages are NOT spotlighted."""
    assert should_spotlight("system") is False


def test_summary_not_spotlighted() -> None:
    """Summary messages are NOT spotlighted."""
    assert should_spotlight("summary") is False
