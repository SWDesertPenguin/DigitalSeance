"""Message format translation for AI providers."""

from __future__ import annotations

from src.orchestrator.types import ContextMessage


def to_provider_messages(
    context: list[ContextMessage],
) -> list[dict[str, str]]:
    """Translate ContextMessages to provider message dicts."""
    system_parts: list[str] = []
    messages: list[dict[str, str]] = []

    for msg in context:
        if msg.role == "system":
            system_parts.append(msg.content)
        else:
            messages.append(_format_message(msg))

    if system_parts:
        messages.insert(0, _system_message(system_parts))
    return messages


def _format_message(msg: ContextMessage) -> dict[str, str]:
    """Format a single non-system message."""
    return {"role": msg.role, "content": msg.content}


def _system_message(parts: list[str]) -> dict[str, str]:
    """Combine system parts into one system message."""
    return {"role": "system", "content": "\n\n".join(parts)}
