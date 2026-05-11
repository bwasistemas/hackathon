from __future__ import annotations

import os
from typing import Any, Optional

from openai import OpenAI


def normalize_assistant_content(content: Any) -> str:
    """Chat APIs may return assistant content as a string or as a list of parts (multimodal / newer SDK)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type")
                if btype == "text":
                    parts.append(str(block.get("text", "")))
                elif btype == "refusal":
                    parts.append(str(block.get("refusal", "")))
            else:
                btype = getattr(block, "type", None)
                if btype == "text":
                    parts.append(str(getattr(block, "text", "") or ""))
                elif btype == "refusal":
                    parts.append(str(getattr(block, "refusal", "") or ""))
        return "".join(parts).strip()
    return str(content).strip()


class OpenAIClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_id: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        response_format: dict | None = None,
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.response_format = response_format

    def create_chat_completion(self, **kwargs: Any) -> Any:
        try:
            return self._client.chat.completions.create(**kwargs)
        except AttributeError:
            return self._client.responses.create(**kwargs)


def build_llm_client(
    api_key: str,
    base_url: str,
    model_id: str | None = None,
    max_tokens: int = 1000,
    temperature: float = 0.7,
    response_format: dict | None = None,
) -> Optional[OpenAIClient]:
    """Build and return an OpenAI client wrapper."""
    if not api_key:
        return None

    return OpenAIClient(
        api_key=api_key,
        base_url=base_url,
        model_id=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format=response_format,
    )


def file_to_content_blocks(path: str) -> list[dict[str, Any]]:
    """Build content blocks for file metadata."""
    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        media: dict[str, Any] = {
            "document": {
                "format": "pdf",
                "name": name,
                "source": {"bytes": data},
            }
        }
    else:
        image_format = {
            ".png": "png",
            ".jpg": "jpeg",
            ".jpeg": "jpeg",
            ".gif": "gif",
            ".webp": "webp",
        }.get(ext, "jpeg")
        media = {
            "image": {
                "format": image_format,
                "source": {"bytes": data},
            }
        }
    return [
        {"text": "Extract visible text and describe the diagram pattern as instructed."},
        media,
    ]
