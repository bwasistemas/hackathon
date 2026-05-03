import pytest

import app.adapters.outbound.strands_multi_agents_adapter as sma
from app.domain.exceptions import LlmAnalysisError


def test_text_from_message_handles_none_and_str():
    """`_text_from_message` should normalize None/string messages into plain text."""
    assert sma._text_from_message(None) == ""
    assert sma._text_from_message("hi") == "hi"


def test_text_from_message_handles_dict_blocks():
    """`_text_from_message` should join dict content blocks (text blocks) with newlines."""
    msg = {"role": "assistant", "content": [{"text": "a"}, {"text": "b"}]}
    assert sma._text_from_message(msg) == "a\nb"


def test_text_from_message_handles_list_content():
    """`_text_from_message` should handle list content containing str and dict blocks."""
    msg = {"role": "assistant", "content": ["a", {"text": "b"}]}
    assert sma._text_from_message(msg) == "a\nb"


def test_agent_output_to_str_handles_str_and_dict():
    """`_agent_output_to_str` should return strings as-is and JSON-encode dict outputs."""
    assert sma._agent_output_to_str("x") == "x"
    out = sma._agent_output_to_str({"a": 1})
    assert '"a"' in out
    assert "1" in out


def test_extract_conversation_history_formats_lines():
    """`extract_conversation_history` should format node history as `agent_name: message` lines."""
    class Node:
        def __init__(self, node_id):
            self.node_id = node_id

    class NodeResult:
        def __init__(self, agent_name, message):
            self.agent_name = agent_name
            self.result = type("R", (), {"message": message})()

    swarm_result = type(
        "SwarmResult",
        (),
        {
            "results": {
                "n1": NodeResult("architect", {"content": [{"text": "hello"}]}),
                "n2": NodeResult("developer", "world"),
            },
            "node_history": [Node("n1"), Node("n2")],
        },
    )()

    history = sma.extract_conversation_history(swarm_result)
    assert "architect: hello" in history
    assert "developer: world" in history


@pytest.mark.asyncio
async def test_swarm_llm_adapter_analyze_success(monkeypatch):
    """`SwarmLlmAdapter.analyze` should invoke the swarm and parse the report JSON into `AnalysisResult`."""
    class FakeSwarm:
        async def invoke_async(self, prompt):
            return object()

    monkeypatch.setattr(
        sma,
        "build_report_agent",
        lambda swarm_result: '{"components":[],"risks":[],"summary":"ok"}',
    )

    adapter = sma.SwarmLlmAdapter(swarm=FakeSwarm())
    result = await adapter.analyze("text", source_hint="img")
    assert result.summary == "ok"


@pytest.mark.asyncio
async def test_swarm_llm_adapter_analyze_wraps_exceptions(monkeypatch):
    """Exceptions from swarm invocation should be wrapped as `LlmAnalysisError`."""
    class FakeSwarm:
        async def invoke_async(self, prompt):
            raise RuntimeError("boom")

    adapter = sma.SwarmLlmAdapter(swarm=FakeSwarm())
    with pytest.raises(LlmAnalysisError):
        await adapter.analyze("text")

