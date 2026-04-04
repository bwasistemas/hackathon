"""Map Strands SDK message / AgentResult shapes to plain text (outbound adapter concern).

Keeps Strands wire-format handling out of application and domain layers.
"""
from __future__ import annotations

from typing import Any


def text_from_message(message: Any) -> str:
    """Normalize Strands message dict/object to plain text for prompts or downstream parsing."""
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        blocks = message.get("content") or []
        parts: list[str] = []
        for block in blocks:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    content = getattr(message, "content", None)
    if content is None:
        return str(message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return text_from_message({"role": "assistant", "content": content})
    return str(content)


def agent_output_to_str(result: Any) -> str:
    """Strands Agent() may return str or AgentResult with a message payload."""
    if isinstance(result, str):
        return result
    msg = getattr(result, "message", None)
    if msg is not None:
        return text_from_message(msg)
    return str(result)
