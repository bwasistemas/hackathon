import os
from typing import Any, Optional

from strands import Agent
from strands.models.openai import OpenAIModel

from app.config import load_settings

settings = load_settings()


def build_llm_client(
    api_key: str,
    base_url: str,
    model_id: str = settings.llm_model,
    max_tokens: int = 1000,
    temperature: float = 0.7,
    response_format: dict = None,
) -> Optional[OpenAIModel]:
    """Build and return an OpenAI model client for Strands."""
    if not api_key:
        return None
    try:
        params = {
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
            model_id=model_id,
            params=params,
        )
    except TypeError:
        return None


SYSTEM_PROMPT = """
                ## PERSONA
                You are a helpful assistant that extracts text from images and PDFs that represent architecture diagrams.

                ## INSTUCTIONS
                Analyze the image or PDF and return the pattern used in the diagram and the language used in the diagram.
                Create a description of the diagram analyzing the components and the relationships between them.


                ## EXAMPLES
                The diagram language is a UML class diagram. The diagram represents a MVC architecture with a controller, a model and a view.
                The diagram language is C4 model. The diagram represents a MVC architecture with a controller, a model and a view.
                The diagram language is BPMN. The diagram represents a MVC architecture with a controller, a model and a view.

                ## RULES
                YOU MUST RETURN THE LANGUAGE USED IN THE DIAGRAM.
                YOU MUST RETURN THE PATTERN USED IN THE DIAGRAM.
                """


def _file_to_content_blocks(path: str) -> list[dict[str, Any]]:
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


class LlmOCRAdapter:
    def __init__(self):
        self._client = build_llm_client(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model_id=settings.llm_ocr,
            max_tokens=3000,
            temperature=0,
        )

    async def analyze_diagram(self, file: str) -> str:
        extractor_agent = Agent(
            name="extractor",
            system_prompt=SYSTEM_PROMPT,
            model=self._client,
        )

        blocks = _file_to_content_blocks(file)
        result = extractor_agent(blocks)
        return str(result)
