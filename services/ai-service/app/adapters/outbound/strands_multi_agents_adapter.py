"""OpenAI SDK adapter implementing LlmAnalyzerPort."""
import logging

from strands import Agent
from strands.multiagent import Swarm

from app.adapters.outbound.helpers.llm import build_llm_client
from app.config import load_settings
from app.application.ports import LlmAnalyzerPort
from app.domain.exceptions import LlmAnalysisError, LlmNotConfiguredError
from app.domain.models import AnalysisResult

from app.adapters.outbound.llm_json_parser import parse_analysis_json

settings = load_settings()
logger = logging.getLogger(__name__)

ARCHITECT_PROMPT = """
    You are a senior software architect and review specialist.  
    You will receive OCR text extracted from architecture diagrams (images or PDFs).  
    The OCR may contain errors, missing connections, or misaligned labels.  

    Your task is to analyze the architecture from this potentially noisy text. Follow these steps:

    1. **Reconstruct the diagram structure**  
    - Infer components/services, their types (e.g., database, API gateway, queue, microservice).  
    - Identify directional flows, dependencies, and communication patterns (sync/async, batch, event-driven).

    2. **Perform risk detection**  
    - List at least 3 potential architectural risks (e.g., single point of failure, data inconsistency, scalability bottleneck, security exposure).  
    - For each risk, suggest a mitigation strategy.

    3. **Explain the architecture in detail**  
    - Write a clear, structured explanation (2-3 paragraphs).  
    - Cover: overall purpose, key interactions, data flow, and any notable patterns (e.g., CQRS, saga, pub/sub).

    4. **Output format**  
    - Use markdown with headings:  
        - `## Reconstructed Structure` (bullet list or table)  
        - `## Detected Risks` (table: Risk | Mitigation)  
        - `## Architecture Explanation` (prose)

    Handle ambiguous OCR gracefully: state assumptions explicitly (e.g., “Assuming 'Auth Servc' refers to 'Auth Service'”).  
"""

INFRASTRUCTURE_PROMPT = """
    You are a senior infrastructure review specialist.  
    You will receive OCR text extracted from architecture diagrams (images or PDFs).  
    The OCR may contain errors, missing connections, or misaligned labels — handle this gracefully.

    Your focus: **infrastructure components, data flow, and deployment concerns**.

    Follow these steps:

    1. **Extract infrastructure components**  
    - Identify: compute (VMs, containers, serverless), storage (block, object, databases), networking (load balancers, CDN, VPC, DNS), and orchestration (K8s, ECS, etc.).  
    - Note missing or ambiguous components with assumptions (e.g., “Assuming 'Kube' refers to Kubernetes”).

    2. **Map data flow**  
    - Trace request/event paths: ingress → service → storage → egress.  
    - Identify protocols (HTTP, gRPC, JDBC, AMQP) and data transformations (ETL, streaming).  
    - Flag single points of failure in the flow.

    3. **Analyze deployment concerns**  
    - Evaluate: high availability, disaster recovery, scaling strategy (horizontal/vertical), secrets management, observability (logs, metrics, traces).  
    - List at least 2 deployment risks (e.g., stateful pod without persistent volume, lack of health checks).
"""

DEVELOPER_PROMPT = """
    You are a senior developer review specialist and hands-on architect.
    You will receive OCR text extracted from architecture diagrams (images or PDFs).
    The OCR may contain errors, missing connections, or misaligned labels — handle this gracefully.

    Your focus: developer-facing architecture, integrations, and implementation details.

    Follow these steps:

    1. Extract developer-facing components
    - Identify: APIs (REST, GraphQL, gRPC), SDKs/libraries, message queues (Kafka, RabbitMQ), databases (with query patterns), event streams, and external dependencies.
    - For each component, note version assumptions (e.g., "Assuming 'Postgres' means PostgreSQL 14+").

    2. Analyze integrations
    - List each integration point with:
        - Protocol/contract (OpenAPI, Protobuf, Avro)
        - Authentication method (OAuth2, API keys, mTLS)
        - Error handling strategy (retries, circuit breakers, dead letter queues)
    - Flag ambiguous integrations (e.g., "Arrow from Service A to Service B — sync or async?" → state assumption).

    3. Identify important implementation details
    - Extract or infer:
        - Transaction boundaries and idempotency
        - Caching strategy (Redis, CDN, in-memory)
        - Background jobs / cron / workers
        - Data validation and serialization format (JSON, Protobuf, Avro)
        - State management (stateless vs. stateful)
    - Highlight at least 2 potential developer pitfalls (e.g., "No retry logic shown for failed API calls", "Missing schema registry for Kafka").

    ## Implementation Details
    - Transactions: ...
    - Caching: ...
    - Background jobs: ...
    - Serialization: ...
    - State: ...

    ## Developer Pitfalls
    1. Pitfall: ... | Fix: ...
    2. Pitfall: ... | Fix: ...

    ## Code-Level Recommendations
    - (e.g., "Use idempotency keys for POST /payment", "Implement exponential backoff for queue consumers")

    State all OCR assumptions explicitly (e.g., "Assuming 'msg broker' means RabbitMQ").
"""

def build_multi_agents() -> Swarm:
    """Build and return a Swarm with specialized agents for architecture analysis."""
    openai_model = build_llm_client(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )

    # Create specialized agents
    architect = Agent(
        name="architect",
        system_prompt=(ARCHITECT_PROMPT),
        model=openai_model
    )
    infrastructure = Agent(
        name="infrastructure",
        system_prompt=(INFRASTRUCTURE_PROMPT),
        model=openai_model
    )
    developer = Agent(
        name="developer",
        system_prompt=(DEVELOPER_PROMPT),
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
    openai_model = build_llm_client(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,
        max_tokens=12000,  # Increased for longer history
        response_format={"type": "json_object"},
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
    Do not include analysis or any text outside of the JSON. Only format the output in the specified JSON,
    in Brazilian Portuguese."""

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

    async def analyze(self, text: str, source_hint: str | None = None) -> AnalysisResult:
        """Analyze the given text using the swarm and generate a report."""

        prompt_parts = [
            "Analyze this architecture diagram from OCR output.",
            "The text may come from a PDF or image diagram.",
        ]
        if source_hint:
            prompt_parts.append(f"Source hint: {source_hint}.")
        prompt_parts.append(text)
        prompt = "\n".join(prompt_parts)

        async def _call() -> AnalysisResult:
            response = await self._swarm.invoke_async(prompt)
            # Pass the full swarm result to build_report_agent for history analysis
            json_content = build_report_agent(response)
            return parse_analysis_json(json_content)

        try:
            return await _call()
        except LlmNotConfiguredError:
            raise
        except Exception as e:
            raise LlmAnalysisError(str(e)) from e
