"""Parse architecture analysis JSON from LLM output (often wrapped in markdown fences)."""
import ast
import json
import re
from json import JSONDecoder
from pydantic import AliasChoices, BaseModel, Field, ValidationError

from app.domain.models import AnalysisResult, Component, Risk

_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


class ComponentSchema(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)


class RiskSchema(BaseModel):
    severity: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=1000)
    # Models often omit or use PT keys; strict parse then falls back to loose — keep optional here too.
    recommendation: str = Field(
        default="",
        max_length=1000,
        validation_alias=AliasChoices(
            "recommendation",
            "recomendacao",
            "recomendação",
            "mitigacao",
            "mitigação",
            "remediation",
            "sugestao",
            "sugestão",
        ),
    )


class AnalysisSchema(BaseModel):
    components: list[ComponentSchema] = Field(min_items=0, max_items=50)
    risks: list[RiskSchema] = Field(min_items=0, max_items=20)
    summary: str = Field(
        default="",
        max_length=5000,
        validation_alias=AliasChoices("summary", "resumo"),
    )
    source_assessment: str = Field(
        default="",
        max_length=4000,
        validation_alias=AliasChoices(
            "source_assessment",
            "avaliacao_fonte",
            "avaliação_fonte",
            "interpretacao_entrada",
            "interpretação_entrada",
            "avaliacao_ocr",
            "avaliação_ocr",
            "analise_da_entrada",
            "análise_da_entrada",
        ),
    )


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


def _fallback_recommendation_pt(severity: str, description: str) -> str:
    """When the model omits recommendation, avoid empty UI — generic but actionable PT text."""
    desc = (description or "").strip()
    sev = (severity or "Média").strip()
    if desc:
        return (
            f"Avaliar impacto deste risco (gravidade: {sev}) com a equipa, definir controles proporcionais "
            "(monitorização, revisão de desenho ou correções incrementais) e validar antes de produção."
        )
    return (
        "Tratar com prioridade alinhada à gravidade indicada: documentar suposições, aplicar controles adequados "
        "e rever na próxima revisão arquitetural."
    )


def parse_analysis_json(content: str) -> AnalysisResult:
    try:
        parsed = _loads_json_lenient(content)
    except (json.JSONDecodeError, SyntaxError, ValueError):
        return AnalysisResult(
            components=[],
            risks=[],
            summary="Analysis unavailable: parsing error",
            source_assessment="",
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
            description = (
                item.get("description")
                or item.get("descricao")
                or item.get("descrição")
                or item.get("details")
                or item.get("issue")
                or item.get("problem")
                or item.get("titulo")
                or item.get("title")
                or ""
            )
            recommendation = _extract_risk_recommendation(item)
            recommendation = str(recommendation).strip() if recommendation else ""
            if not recommendation and (severity or description):
                recommendation = _fallback_recommendation_pt(str(severity), str(description))
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
            summary="Analysis unavailable: parsing error",
            source_assessment="",
        )

    sa = _extract_source_assessment(parsed)
    return AnalysisResult(
        components=components,
        risks=risks,
        summary=summary,
        source_assessment=sa,
    )


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
            recommendation=(r.recommendation or "").strip()
            or _fallback_recommendation_pt(r.severity, r.description),
        )
        for r in validated.risks
    ]
    return AnalysisResult(
        components=components,
        risks=risks,
        summary=validated.summary,
        source_assessment=(validated.source_assessment or "").strip(),
    )


def _extract_risk_recommendation(item: dict) -> str:
    """Map common EN/PT keys and nested shapes to a single recommendation string."""
    direct_keys = (
        "recommendation",
        "recomendacao",
        "recomendação",
        "mitigation",
        "mitigacao",
        "mitigação",
        "remediation",
        "remediação",
        "acao_corretiva",
        "acao_recomendada",
        "contramedida",
        "contorno",
        "solucao",
        "solução",
        "sugestao",
        "sugestão",
        "plano_de_acao",
        "medidas",
        "action",
        "actions",
    )
    for k in direct_keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    # Lists of actions / next steps (some models)
    for list_key in (
        "recommended_actions",
        "acoes_recomendadas",
        "ações_recomendadas",
        "actions",
        "passos",
        "next_steps",
        "proximos_passos",
        "próximos_passos",
    ):
        lst = item.get(list_key)
        if isinstance(lst, list) and lst:
            parts: list[str] = []
            for x in lst:
                if isinstance(x, str) and x.strip():
                    parts.append(x.strip())
                elif isinstance(x, dict):
                    t = x.get("description") or x.get("text") or x.get("action") or x.get("step")
                    if t is not None and str(t).strip():
                        parts.append(str(t).strip())
            if parts:
                return "; ".join(parts)
    # Nested mitigation object (some models)
    mit = item.get("mitigation") or item.get("mitigacao")
    if isinstance(mit, dict):
        inner = mit.get("description") or mit.get("steps") or mit.get("text")
        if inner is not None and str(inner).strip():
            return str(inner).strip()
    if isinstance(mit, str) and mit.strip():
        return mit.strip()
    return ""


def _extract_source_assessment(parsed: dict) -> str:
    keys = (
        "source_assessment",
        "avaliacao_fonte",
        "avaliação_fonte",
        "interpretacao_entrada",
        "interpretação_entrada",
        "avaliacao_ocr",
        "avaliação_ocr",
        "analise_da_entrada",
        "análise_da_entrada",
    )
    for k in keys:
        v = parsed.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""
