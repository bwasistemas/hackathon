"""Helpers shared by the Ragas evaluation suite.

Two responsibilities:

1. Render an `AnalysisResult` into a single response string the LLM-as-a-judge
   can reason over (Ragas evaluates plain text, while our domain returns a
   structured dataclass).
2. Build `SingleTurnSample` records that can be packed into an
   `EvaluationDataset`.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Iterable

from ragas.dataset_schema import SingleTurnSample

from app.domain.models import AnalysisResult


def analysis_result_to_response_text(result: AnalysisResult) -> str:
    """Serialize an `AnalysisResult` into a markdown-flavored response.

    The shape mirrors what an end-user reading the analysis would see, so that
    Ragas judges score the content the user actually consumes — not the raw
    JSON wire format.
    """
    lines: list[str] = []

    if result.summary:
        lines.append("## Resumo")
        lines.append(result.summary.strip())
        lines.append("")

    if result.components:
        lines.append("## Componentes identificados")
        for comp in result.components:
            name = comp.name.strip() or "(sem nome)"
            ctype = comp.component_type.strip() or "(tipo desconhecido)"
            description = comp.description.strip() or "(sem descrição)"
            lines.append(f"- **{name}** ({ctype}): {description}")
        lines.append("")

    if result.risks:
        lines.append("## Riscos detectados")
        for risk in result.risks:
            severity = risk.severity.strip() or "(severidade não informada)"
            description = risk.description.strip() or "(sem descrição)"
            recommendation = risk.recommendation.strip() or "(sem recomendação)"
            lines.append(
                f"- [{severity}] {description}\n  - Recomendação: {recommendation}"
            )
        lines.append("")

    if not lines:
        return "(análise vazia)"

    return "\n".join(lines).strip()


def analysis_result_to_json(result: AnalysisResult) -> str:
    """Compact JSON view, useful for criteria that look at structure."""
    return json.dumps(asdict(result), ensure_ascii=False, indent=2)


def build_single_turn_sample(
    *,
    user_input: str,
    response: AnalysisResult | str,
    retrieved_contexts: Iterable[str] | None = None,
    reference: str | None = None,
) -> SingleTurnSample:
    """Construct a Ragas `SingleTurnSample` from an `AnalysisResult` or string."""
    response_text = (
        response
        if isinstance(response, str)
        else analysis_result_to_response_text(response)
    )

    return SingleTurnSample(
        user_input=user_input,
        response=response_text,
        retrieved_contexts=list(retrieved_contexts) if retrieved_contexts else None,
        reference=reference,
    )
