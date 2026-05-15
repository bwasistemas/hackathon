"""Swarm / Strands multi-agent adapter implementing LlmAnalyzerPort."""
import json
import logging
from typing import Any

from app.application.ports import LlmAnalyzerPort
from app.domain.exceptions import LlmAnalysisError
from app.domain.models import AnalysisResult
from app.adapters.outbound.llm_json_parser import parse_analysis_json

logger = logging.getLogger(__name__)


def _text_from_message(message: Any) -> str:
    """Normalize a Strands message dict/object to plain text."""
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        blocks = message.get("content") or []
        parts: list[str] = []
        for block in blocks:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    content = getattr(message, "content", None)
    if content is None:
        return str(message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _text_from_message({"role": "assistant", "content": content})
    return str(content)


def _agent_output_to_str(result: Any) -> str:
    """Serialize an agent output to a string (dicts become JSON)."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return json.dumps(result)
    msg = getattr(result, "message", None)
    if msg is not None:
        return _text_from_message(msg)
    return str(result)


def extract_conversation_history(swarm_result: Any) -> str:
    """Format swarm node history as 'agent_name: message' lines."""
    results = getattr(swarm_result, "results", {})
    node_history = getattr(swarm_result, "node_history", [])
    lines: list[str] = []
    for node in node_history:
        node_id = getattr(node, "node_id", None)
        node_result = results.get(node_id)
        if node_result is None:
            continue
        agent_name = getattr(node_result, "agent_name", node_id)
        result_obj = getattr(node_result, "result", None)
        message = getattr(result_obj, "message", None) if result_obj is not None else None
        lines.append(f"{agent_name}: {_text_from_message(message)}")
    return "\n".join(lines)


def build_report_agent(swarm_result: Any) -> str:
    """Extract the final JSON report string from a swarm result."""
    return extract_conversation_history(swarm_result)


class SwarmLlmAdapter(LlmAnalyzerPort):
    """LLM adapter backed by a multi-agent swarm (e.g. AWS Strands)."""

    def __init__(self, swarm: Any) -> None:
        self._swarm = swarm

    async def analyze(self, text: str, source_hint: str | None = None) -> AnalysisResult:
        prompt = text
        if source_hint:
            prompt = f"{text}\nSource hint: {source_hint}."
        try:
            swarm_result = await self._swarm.invoke_async(prompt)
            raw_json = build_report_agent(swarm_result)
            return parse_analysis_json(raw_json)
        except LlmAnalysisError:
            raise
        except Exception as exc:
            logger.error("Swarm analysis failed", exc_info=True)
            raise LlmAnalysisError(str(exc)) from exc
