"""OpenAI SDK adapter implementing LlmAnalyzerPort."""
from typing import Optional
import logging
from strands import Agent
from strands.multiagent import Swarm
from strands.models.openai import OpenAIModel

from app.config import load_settings
from app.application.ports import LlmAnalyzerPort
from app.domain.exceptions import LlmAnalysisError, LlmNotConfiguredError
from app.domain.models import AnalysisResult

from app.adapters.outbound.llm_json_parser import parse_analysis_json

settings = load_settings()
logger = logging.getLogger(__name__)


def build_strands_client(
    api_key: str,
    base_url: str,
    model_id: str = settings.llm_model,
    max_tokens: int = 1000,
    temperature: float = 0.7,
    response_format: dict = None
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
            params=params
        )
    except TypeError:
        return None


def build_multi_agents() -> Swarm:
    """Build and return a Swarm with specialized agents for architecture analysis."""
    openai_model = build_strands_client(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )

    # Create specialized agents
    architect = Agent(
        name="architect",
        system_prompt="You are a software architect review specialist...",
        model=openai_model
    )
    infrastructure = Agent(
        name="infrastructure",
        system_prompt="You are a infrastructure review specialist...",
        model=openai_model
    )
    developer = Agent(
        name="developer",
        system_prompt="You are a developer review specialist...",
        model=openai_model
    )

    # Create a swarm with these agents, starting with the architect
    return Swarm(
        [architect, infrastructure, developer],
        entry_point=architect,  # Start with the architect
        max_handoffs=settings.max_handoffs,
        max_iterations=settings.max_iterations,
        execution_timeout=settings.execution_timeout,
        node_timeout=settings.node_timeout,
        repetitive_handoff_detection_window=settings.repetitive_handoff_detection_window,
        repetitive_handoff_min_unique_agents=settings.repetitive_handoff_min_unique_agents
    )


def extract_conversation_history(swarm_result) -> str:
    """Extract the full conversation history from the swarm result."""
    results = getattr(swarm_result, "results", None) or {}
    history = getattr(swarm_result, "node_history", None) or []

    conversation_parts = []
    for node in history:
        node_id = node.node_id
        node_result = results.get(node_id)
        if node_result:
            agent_result = node_result.result
            message = _text_from_message(getattr(agent_result, "message", None))
            agent_name = getattr(node_result, "agent_name", "Unknown")
            conversation_parts.append(f"{agent_name}: {message}")

    return "\n".join(conversation_parts)


def build_report_agent(swarm_result) -> str:
    """Build a report agent that analyzes the full conversation history and generates a JSON report."""
    openai_model = build_strands_client(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,
        max_tokens=4000,  # Increased for longer history
        response_format={"type": "json_object"}
    )

    system_prompt = """You are a software architect expert on architecture diagrams.
    Receive the full conversation history from the multi-agent analysis and strictly return, in the exact JSON format below,
    the identification of components/services (databases, APIs, frontends, etc.), potential architectural risks:
    {
    "components": [
        {"name": "...", "type": "...", "description": "..."}
    ],
    "risks": [
        {"severity": "...", "description": "...", "recommendation": "..."}
    ],
    "summary": "detailed text explaining the diagram..."
    }
    Do not include analysis or any text outside of the JSON. Only format the output in the specified JSON, in Brazilian Portuguese."""

    agent = Agent(
        model=openai_model,
        messages=[
            {"role": "system", "content": [{"text": system_prompt}]},
        ],
    )

    history_text = extract_conversation_history(swarm_result)
    user_message = [{"role": "user", "content": [{"text": history_text}]}]
    return _agent_output_to_str(agent(user_message))


def _text_from_message(message) -> str:
    """Normalize Strands message dict/object to plain text."""
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        blocks = message.get("content") or []
        parts = []
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


def _agent_output_to_str(result) -> str:
    """Convert agent result to string."""
    if isinstance(result, str):
        return result
    msg = getattr(result, "message", None)
    if msg is not None:
        return _text_from_message(msg)
    return str(result)


class SwarmLlmAdapter(LlmAnalyzerPort):
    """Adapter for LLM analysis using Strands Swarm."""

    def __init__(self, swarm: Swarm) -> None:
        self._swarm = swarm

    async def analyze(self, text: str) -> AnalysisResult:
        """Analyze the given text using the swarm and generate a report."""
        async def _call() -> AnalysisResult:
            response = await self._swarm.invoke_async(f"Analyze this architecture diagram:\n{text}")
            # Pass the full swarm result to build_report_agent for history analysis
            json_content = build_report_agent(response)
            return parse_analysis_json(json_content)

        try:
            return await _call()
        except LlmNotConfiguredError:
            raise
        except Exception as e:
            raise LlmAnalysisError(str(e)) from e
