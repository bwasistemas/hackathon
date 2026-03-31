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

def build_strands_client(api_key: str, base_url: str, model_id: str = "deepseek/deepseek-v3.2", max_tokens:int = 1000, temperature: float = 0.7) -> Optional[OpenAIModel]:
    if not api_key:
        return None
    try:
        return OpenAIModel(
                client_args={
                    "api_key": api_key,
                    "base_url": base_url,
                },
                # **model_config
                model_id=model_id,
                params={
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            )
    except TypeError:
        return None

def build_multi_agents():
    openAIModel = build_strands_client(
        api_key = settings.openai_api_key,
        base_url = settings.openai_base_url, 
    )

    # Create a specialized agents
    architect = Agent(name="architect", system_prompt="You are a software architect review specialist...", model=openAIModel)
    infrastructure = Agent(name="infrastructure", system_prompt="You are a infrastructure review specialist...", model=openAIModel)
    developer = Agent(name="developer", system_prompt="You are a developer review specialist...", model=openAIModel)
    staff_architect = Agent(name="staff_architect", system_prompt="You are software staff architect review specialist...", model=openAIModel)
    
    # Create a swarm with these agents, starting with the researcher
    return Swarm(
        [architect, infrastructure, developer, staff_architect],
        entry_point=architect,  # Start with the architect
        max_handoffs=20,
        max_iterations=20,
        execution_timeout=60.0,  # 1 minute
        node_timeout=30.0,       # 30 seconds per agent
        repetitive_handoff_detection_window=8,  # There must be >= 3 unique agents in the last 8 handoffs
        repetitive_handoff_min_unique_agents=3
)

def build_report_agent(result:str):
    openAIModel = build_strands_client(
        api_key = settings.openai_api_key,
        base_url = settings.openai_base_url, 
        temperature= 0.1
    )
    
    SYSTEM_PROMPT = """You are a software architect expert on architecture diagrams. 
    Receive the extracted text from a diagram and strictly return, in the exact JSON format below, 
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

    agent = Agent(model=openAIModel,
                  messages=[{"role": "system", "content": [{"text": SYSTEM_PROMPT}]}
    ])

    # Continue the conversation
    return _agent_output_to_str(agent(result))

def _text_from_message(message) -> str:
    """Normalize Strands message dict/object to plain text for model input."""
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

def _agent_output_to_str(result) -> str:
    """Agent() may return str or AgentResult with a message payload."""
    if isinstance(result, str):
        return result
    msg = getattr(result, "message", None)
    if msg is not None:
        return _text_from_message(msg)
    return str(result)

def final_swarm_text(swarm_result) -> str:
    """Last node's assistant text. Avoid next() on empty dict — raises StopIteration, which breaks async callers."""
    results = getattr(swarm_result, "results", None) or {}
    history = getattr(swarm_result, "node_history", None) or []
    if not results:
        return ""
    if not history:
        keys = list(results.keys())
        last_key = keys[-1]
        node_result = results[last_key]
    else:
        last_id = history[-1].node_id
        node_result = results.get(last_id)
        if node_result is None:
            keys = list(results.keys())
            node_result = results[keys[-1]] if keys else None
    if node_result is None:
        return ""

    agent_result = node_result.result
    return _text_from_message(getattr(agent_result, "message", None))

class SwarmLlmAdapter(LlmAnalyzerPort):
    def __init__(
        self,
        swarm: Swarm,
    ) -> None:
        self._swarm = swarm

    async def analyze(self, text: str) -> AnalysisResult:
        async def _call() -> AnalysisResult:
            response = await self._swarm.invoke_async(f"Analyze this architecture diagram:\n{text}")
            content = final_swarm_text(response)
            # Use module logger so uvicorn/docker logs show INFO (root logger may be quiet).
            # logger.error("Swarm raw response (repr): %r", final_swarm_text(response))
            json_content = build_report_agent(content)
            # logger.error("JSON raw response (repr): %r", json_content.result)
            return parse_analysis_json(json_content)

        try:
            return await _call()
        except LlmNotConfiguredError:
            raise
        except Exception as e:
            raise LlmAnalysisError(str(e)) from e
