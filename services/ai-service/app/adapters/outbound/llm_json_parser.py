"""Parse architecture analysis JSON from LLM output (often wrapped in markdown fences)."""
import ast
import json
import re
from json import JSONDecoder
from pydantic import BaseModel, Field, ValidationError

from app.domain.models import AnalysisResult, Component, Risk

_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


class ComponentSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)


class RiskSchema(BaseModel):
    severity: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=1000)
    recommendation: str = Field(min_length=1, max_length=1000)


class AnalysisSchema(BaseModel):
    components: list[ComponentSchema] = Field(min_length=0, max_length=50)
    risks: list[RiskSchema] = Field(min_length=0, max_length=20)
    summary: str = Field(default="", max_length=5000)


def _strip_markdown_json_fence(text: str) -> str:
    text = text.strip()
    m = _FENCE.search(text)
    if m:
        return m.group(1).strip()
    return text


def _loads_json_lenient(raw: str | dict) -> dict:
    """Decode first JSON object; tolerate markdown fences or short preamble text."""
    if isinstance(raw, dict):
        return raw

    s = _strip_markdown_json_fence(raw).strip()
    # If after stripping fences, it starts with {, parse from there
    decoder = JSONDecoder()
    start = s.find("{")
    if start == -1:
        # Try to find JSON anywhere in the text
        json_match = re.search(r'\{.*\}', s, re.DOTALL)
        if json_match:
            s = json_match.group(0)
            start = 0
        else:
            raise json.JSONDecodeError("No JSON object", s, 0)

    try:
        obj, _ = decoder.raw_decode(s[start:])
    except json.JSONDecodeError:
        try:
            obj = ast.literal_eval(s[start:])
        except Exception:
            raise

    if not isinstance(obj, dict):
        raise json.JSONDecodeError("Expected JSON object", s, start)
    return obj


def parse_analysis_json(content: str) -> AnalysisResult:
    try:
        parsed = _loads_json_lenient(content)
    except (json.JSONDecodeError, SyntaxError, ValueError):
        return AnalysisResult(
            components=[],
            risks=[],
            summary="Analysis unavailable: parsing error"
        )

    try:
        validated = AnalysisSchema.model_validate(parsed)
        return _convert_to_domain(validated)
    except ValidationError:
        return _convert_to_domain_loose(parsed)


def _convert_to_domain_loose(parsed: dict) -> AnalysisResult:
    components = []
    raw_components = parsed.get("components") or parsed.get("componentes") or []
    if isinstance(raw_components, dict):
        raw_components = [raw_components]
    if isinstance(raw_components, list):
        for item in raw_components:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("nome") or item.get("component") or ""
            comp_type = item.get("type") or item.get("tipo") or item.get("category") or ""
            description = item.get("description") or item.get("descricao") or item.get("descrição") or item.get("details") or ""
            if name or comp_type or description:
                components.append(
                    Component(
                        name=str(name).strip() or "Componente",
                        component_type=str(comp_type).strip() or "Desconhecido",
                        description=str(description).strip() or "",
                    )
                )

    risks = []
    raw_risks = parsed.get("risks") or parsed.get("riscos") or []
    if isinstance(raw_risks, dict):
        raw_risks = [raw_risks]
    if isinstance(raw_risks, list):
        for item in raw_risks:
            if not isinstance(item, dict):
                continue
            severity = item.get("severity") or item.get("gravidade") or item.get("level") or ""
            description = item.get("description") or item.get("descricao") or item.get("descrição") or item.get("details") or ""
            recommendation = item.get("recommendation") or item.get("recomendacao") or item.get("recomendação") or item.get("suggestion") or ""
            if severity or description or recommendation:
                risks.append(
                    Risk(
                        severity=str(severity).strip() or "Média",
                        description=str(description).strip() or "",
                        recommendation=str(recommendation).strip() or "",
                    )
                )

    summary = parsed.get("summary") or parsed.get("resumo") or parsed.get("descricao") or parsed.get("description") or ""
    if not isinstance(summary, str):
        summary = str(summary)
    summary = summary.strip()

    if not components and not risks and not summary:
        return AnalysisResult(
            components=[],
            risks=[],
            summary="Analysis unavailable: parsing error"
        )

    return AnalysisResult(components=components, risks=risks, summary=summary)


def _convert_to_domain(validated: AnalysisSchema) -> AnalysisResult:
    components = [
        Component(
            name=c.name,
            component_type=c.type,
            description=c.description,
        )
        for c in validated.components
    ]
    risks = [
        Risk(
            severity=r.severity,
            description=r.description,
            recommendation=r.recommendation,
        )
        for r in validated.risks
    ]
    return AnalysisResult(components=components, risks=risks, summary=validated.summary)
