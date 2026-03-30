"""OpenAI SDK adapter implementing LlmAnalyzerPort."""
import asyncio
import json
from typing import Optional
import logging
import os
from strands import Agent
from strands.multiagent import Swarm
from strands.models.openai import OpenAIModel
from strands_tools import calculator

from app.config import load_settings
from app.application.ports import LlmAnalyzerPort
from app.domain.exceptions import LlmAnalysisError, LlmNotConfiguredError
from app.domain.models import AnalysisResult, Component, Risk

settings = load_settings()

def build_strands_client(api_key: str, base_url: str, model_id: str = "gpt-4o", max_tokens:int = 1000, temperature: float = 0.7) -> Optional[OpenAIModel]:
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

    # Create specialized agents
    architect = Agent(name="architect", system_prompt="You are a software architect review specialist...", model=openAIModel)
    infrastructure = Agent(name="infrastructure", system_prompt="You are a infrastructure review specialist...", model=openAIModel)
    developer = Agent(name="developer", system_prompt="You are a developer review specialist...", model=openAIModel)
    staff_architect = Agent(name="staff_architect", system_prompt="You are a software staff architect review specialist...", model=openAIModel)
    
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
    return agent(result)

class SwarmLlmAdapter(LlmAnalyzerPort):
    def __init__(
        self,
        swarm: Swarm,
    ) -> None:
        self._swarm = swarm

    async def analyze(self, text: str) -> AnalysisResult:
        if not self._client:
            raise LlmNotConfiguredError(
                "AI service not configured. Set OPENAI_API_KEY."
            )

        async def _call() -> AnalysisResult:
            response = await self._swarm.invoke_async(f"Analyze this architecture diagram:\n{text}")
            content = response.result or ""
            json_content = build_report_agent(content)
            return _parse_llm_json(json_content)

        try:
            return await asyncio.to_thread(_call)
        except LlmNotConfiguredError:
            raise
        except Exception as e:
            raise LlmAnalysisError(str(e)) from e

def _parse_llm_json(content: str) -> AnalysisResult:
    try:
        parsed = json.loads(content)
        components = [
            Component(
                name=c.get("name", ""),
                component_type=c.get("type", ""),
                description=c.get("description", ""),
            )
            for c in parsed.get("components", [])
        ]
        risks = [
            Risk(
                severity=r.get("severity", ""),
                description=r.get("description", ""),
                recommendation=r.get("recommendation", ""),
            )
            for r in parsed.get("risks", [])
        ]
        summary = parsed.get("summary", content)
        return AnalysisResult(components=components, risks=risks, summary=summary)
    except json.JSONDecodeError:
        return AnalysisResult(
            components=[],
            risks=[],
            summary="Error parsing AI response: " + content,
        )
