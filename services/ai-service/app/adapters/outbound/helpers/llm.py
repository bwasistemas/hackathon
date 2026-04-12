import os
from typing import Any, Optional

from strands.models.openai import OpenAIModel

from app.config import load_settings


def build_llm_client(
    api_key: str,
    base_url: str,
    model_id: str | None = None,
    max_tokens: int = 1000,
    temperature: float = 0.7,
    response_format: dict | None = None,
) -> Optional[OpenAIModel]:
    """Build and return an OpenAI model client for Strands."""
    if not api_key:
        return None
    resolved_model_id = model_id if model_id is not None else load_settings().llm_model
    try:
        params: dict[str, Any] = {
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            params["response_format"] = response_format
        return OpenAIModel(
            client_args={
                "api_key": api_key,
                "base_url": base_url,
            },
            model_id=resolved_model_id,
            params=params,
        )
    except TypeError:
        return None


def file_to_content_blocks(path: str) -> list[dict[str, Any]]:
    """Build Strands ContentBlock list (not OpenAI chat parts)."""
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
