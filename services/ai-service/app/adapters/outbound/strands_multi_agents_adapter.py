"""OpenAI adapter implementing LlmAnalyzerPort for the AI service."""
import asyncio
import logging
import os
from typing import Any

from app.adapters.outbound.helpers.llm import OpenAIClient, build_llm_client, normalize_assistant_content
from app.application.ports import LlmAnalyzerPort
from app.domain.exceptions import LlmAnalysisError, LlmNotConfiguredError
from app.domain.models import AnalysisResult
from app.adapters.outbound.llm_json_parser import parse_analysis_json
from app.config import load_settings

settings = load_settings()
logger = logging.getLogger(__name__)

_ANALYSIS_JSON_OBJECT = os.getenv("LLM_ANALYSIS_JSON_OBJECT", "true").lower() in ("1", "true", "yes", "on")

ANALYSIS_PROMPT = """
You are a senior software architect and analysis specialist.
You will receive text describing an architecture diagram. That text may come from multimodal LLM extraction
from images/PDFs or from classical OCR — treat it as the best available description of the diagram;
diagrams that are mostly shapes may yield little text — infer cautiously from what is present.

Output only valid JSON with these keys:
- source_assessment (string, Portuguese): 3–6 sentences explaining (a) how complete/useful the OCR text was,
  (b) what you assumed or inferred beyond literal OCR, and (c) confidence limits. This is NOT the executive summary.
- components: list of objects {name, type, description}
- risks: list of objects {severity, description, recommendation}
  • Each risk MUST include a non-empty "recommendation" field with a concrete, actionable mitigation in Portuguese
    (you may also duplicate the same text under "recomendacao" if you prefer bilingual keys, but "recommendation" is required).
- summary (string, Portuguese): concise executive summary of the architecture.

Example risk shape:
{"severity":"Alta","description":"...","recommendation":"Implementar filas assíncronas entre X e Y para..."}

Always respond in Brazilian Portuguese except JSON keys, which must be exactly as specified above.
"""


def build_multi_agents() -> OpenAIClient:
    """Build and return a configured OpenAI client."""
    client = build_llm_client(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        model_id=settings.llm_model,
        max_tokens=3000,
        temperature=0.0,
    )
    if client is None:
        raise LlmNotConfiguredError("OpenAI API key is not configured")
    return client


def _build_messages(text: str, source_hint: str | None = None) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": ANALYSIS_PROMPT.strip()},
        {"role": "user", "content": text},
    ]
    if source_hint:
        messages.append({"role": "user", "content": f"Source hint: {source_hint}."})
    return messages


def _response_to_text(response: Any) -> str:
    if hasattr(response, "choices") and response.choices:
        msg = response.choices[0].message
        return normalize_assistant_content(getattr(msg, "content", None))
    if isinstance(response, dict):
        choices = response.get("choices")
        if choices and isinstance(choices, list):
            message = choices[0].get("message")
            if isinstance(message, dict):
                return normalize_assistant_content(message.get("content"))
    return normalize_assistant_content(str(response))


class SwarmLlmAdapter(LlmAnalyzerPort):
    """Adapter for LLM analysis using OpenAI chat completions."""

    def __init__(self, client: OpenAIClient) -> None:
        self._client = client

    async def analyze(self, text: str, source_hint: str | None = None) -> AnalysisResult:
        if self._client is None:
            raise LlmNotConfiguredError("LLM client not configured")

        messages = _build_messages(text, source_hint)
        params = {
            "model": getattr(self._client, "model_id", None),
            "messages": messages,
            "max_tokens": getattr(self._client, "max_tokens", 3000),
            "temperature": getattr(self._client, "temperature", 0.0),
        }
        if _ANALYSIS_JSON_OBJECT:
            params["response_format"] = {"type": "json_object"}

        try:
            response = await asyncio.to_thread(self._client.create_chat_completion, **params)
        except Exception as first:
            if _ANALYSIS_JSON_OBJECT and params.get("response_format"):
                logger.warning(
                    "Chat completion with json_object failed (%s); retrying without response_format",
                    first,
                )
                params_retry = {k: v for k, v in params.items() if k != "response_format"}
                try:
                    response = await asyncio.to_thread(self._client.create_chat_completion, **params_retry)
                except Exception as second:
                    logger.error("LLM analysis failed after retry", exc_info=True)
                    raise LlmAnalysisError(str(second)) from second
            else:
                logger.error("LLM analysis failed", exc_info=True)
                raise LlmAnalysisError(str(first)) from first

        try:
            content = _response_to_text(response)
            return parse_analysis_json(content)
        except Exception as e:
            logger.error("LLM response handling failed", exc_info=True)
            raise LlmAnalysisError(str(e)) from e
