"""OpenAI SDK adapter implementing LlmAnalyzerPort."""
import asyncio
import math
import re
from typing import Optional

import tiktoken
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


class LlmInputSanitizer:
    def __init__(self, model: str):
        self.encoding = tiktoken.encoding_for_model(model)
        self.MAX_TOKENS = 6000  # Leave buffer for response
    
    def sanitize_and_validate(self, text: str) -> str:
        # 1. Remove potential injection markers
        suspicious_patterns = [
            r"(?i)(ignore.*instruction|forget.*prompt|override)",
            r"(?i)(execute|run|eval|code)",
        ]
        sanitized = text
        for pattern in suspicious_patterns:
            sanitized = re.sub(pattern, "[REDACTED]", sanitized)
        
        # 2. Count tokens
        tokens = self.encoding.encode(sanitized)
        if len(tokens) > self.MAX_TOKENS:
            raise ValueError(
                f"Input too large: {len(tokens)} tokens > {self.MAX_TOKENS}"
            )
        
        # 3. Enforce maximum entropy (detect randomness/gibberish)
        entropy = self._calculate_entropy(sanitized)
        if entropy > 5.5:  # High entropy = likely junk
            raise ValueError("Input appears to be gibberish or random data")
        
        return sanitized
    
    @staticmethod
    def _calculate_entropy(text: str) -> float:
        from collections import Counter
        if not text:
            return 0
        freq = Counter(text)
        total = len(text)
        entropy = 0
        for count in freq.values():
            p = count / total
            entropy -= p * math.log2(p) if p > 0 else 0
        return entropy


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
        self._sanitizer = LlmInputSanitizer(model)

    async def analyze(self, text: str, source_hint: str | None = None) -> AnalysisResult:
        if not self._client:
            raise LlmNotConfiguredError(
                "AI service not configured. Set OPENAI_API_KEY."
            )

        # Sanitize input
        sanitized_text = self._sanitizer.sanitize_and_validate(text)

        def _call() -> AnalysisResult:
            prompt = [
                "Analyze this architecture diagram from OCR output.",
                "The text may come from a PDF or image diagram.",
            ]
            if source_hint:
                prompt.append(f"Source hint: {source_hint}.")
            prompt.append(sanitized_text)
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": "\n".join(prompt),
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
