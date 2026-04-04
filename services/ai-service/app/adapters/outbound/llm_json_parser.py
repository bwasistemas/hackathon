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
    # If after stripping fences, it starts with {, parse from there
    decoder = JSONDecoder()
    start = s.find("{")
    if start == -1:
        # Try to find JSON anywhere in the text
        import re
        json_match = re.search(r'\{.*\}', s, re.DOTALL)
        if json_match:
            s = json_match.group(0)
            start = 0
        else:
            raise json.JSONDecodeError("No JSON object", s, 0)
    obj, _ = decoder.raw_decode(s[start:])
    if not isinstance(obj, dict):
        raise json.JSONDecodeError("Expected JSON object", s, start)
    return obj


def parse_analysis_json(content: str) -> AnalysisResult:
    try:
        parsed = _loads_json_lenient(content)
        components_data = parsed.get("components") or parsed.get("componentes") or []
        risks_data = parsed.get("risks") or parsed.get("riscos") or []
        components = [
            Component(
                name=c.get("name", "") or c.get("nome", ""),
                component_type=c.get("type", "") or c.get("tipo", ""),
                description=(
                    c.get("description", "")
                    or c.get("descricao", "")
                    or c.get("descrição", "")
                ),
            )
            for c in components_data
        ]
        risks = []
        for r in risks_data:
            rec = (
                r.get("recommendation")
                or r.get("recomendação")
                or r.get("recomendacao")
                or ""
            )
            risks.append(
                Risk(
                    severity=r.get("severity", "") or r.get("gravidade", ""),
                    description=(
                        r.get("description", "")
                        or r.get("descricao", "")
                        or r.get("descrição", "")
                    ),
                    recommendation=rec,
                )
            )
        summary = (
            parsed.get("summary")
            or parsed.get("resumo")
            or parsed.get("summary_text")
            or parsed.get("resumo_da_analise")
            or content
        )
        return AnalysisResult(components=components, risks=risks, summary=summary)
    except (json.JSONDecodeError, ValueError, TypeError):
        return AnalysisResult(
            components=[],
            risks=[],
            summary="Error parsing AI response: " + content,
        )
