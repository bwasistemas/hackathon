"""OpenAI SDK adapter implementing LlmAnalyzerPort."""
import asyncio
from typing import Optional

from openai import OpenAI

from app.application.ports import LlmAnalyzerPort
from app.domain.exceptions import LlmAnalysisError, LlmNotConfiguredError
from app.domain.models import AnalysisResult

from app.adapters.outbound.llm_json_parser import parse_analysis_json

SYSTEM_PROMPT = """You are an expert software architect analyzing architecture diagrams.
Given the extracted text from a diagram, identify:
1. Components/services (databases, APIs, frontends, etc.)
2. Potential architectural risks
3. A brief summary

You MUST return the output strictly as a JSON object matching this exact structure:
{
  "components": [
    {"name": "...", "type": "...", "description": "..."}
  ],
  "risks": [
    {"severity": "...", "description": "...", "recommendation": "..."}
  ],
  "summary": "texto detalhado explicando o diagrama..."
}

Return a structured analysis in Portuguese."""


def build_openai_client(api_key: str, base_url: str) -> Optional[OpenAI]:
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key, base_url=base_url)
    except TypeError:
        return OpenAI(api_key=api_key)


class OpenAiLlmAdapter(LlmAnalyzerPort):
    def __init__(
        self,
        client: Optional[OpenAI],
        model: str,
    ) -> None:
        self._client = client
        self._model = model

    async def analyze(self, text: str) -> AnalysisResult:
        if not self._client:
            raise LlmNotConfiguredError(
                "AI service not configured. Set OPENAI_API_KEY."
            )

        def _call() -> AnalysisResult:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Analyze this architecture diagram:\n{text}",
                    },
                ],
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            return parse_analysis_json(content)

        try:
            return await asyncio.to_thread(_call)
        except LlmNotConfiguredError:
            raise
        except Exception as e:
            raise LlmAnalysisError(str(e)) from e
