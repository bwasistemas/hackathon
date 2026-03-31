"""Parse architecture analysis JSON from LLM output (often wrapped in markdown fences)."""
import json
import re
from json import JSONDecoder

from app.domain.models import AnalysisResult, Component, Risk

_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _strip_markdown_json_fence(text: str) -> str:
    text = text.strip()
    m = _FENCE.search(text)
    if m:
        return m.group(1).strip()
    return text


def _loads_json_lenient(raw: str) -> dict:
    """Decode first JSON object; tolerate markdown fences or short preamble text."""
    s = _strip_markdown_json_fence(raw).strip()
    decoder = JSONDecoder()
    start = s.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object", s, 0)
    obj, _ = decoder.raw_decode(s[start:])
    if not isinstance(obj, dict):
        raise json.JSONDecodeError("Expected JSON object", s, start)
    return obj


def parse_analysis_json(content: str) -> AnalysisResult:
    try:
        parsed = _loads_json_lenient(content)
        components = [
            Component(
                name=c.get("name", ""),
                component_type=c.get("type", ""),
                description=c.get("description", ""),
            )
            for c in parsed.get("components", [])
        ]
        risks = []
        for r in parsed.get("risks", []):
            rec = r.get("recommendation") or r.get("recommendação", "")
            risks.append(
                Risk(
                    severity=r.get("severity", ""),
                    description=r.get("description", ""),
                    recommendation=rec,
                )
            )
        summary = parsed.get("summary", content)
        return AnalysisResult(components=components, risks=risks, summary=summary)
    except (json.JSONDecodeError, ValueError, TypeError):
        return AnalysisResult(
            components=[],
            risks=[],
            summary="Error parsing AI response: " + content,
        )
