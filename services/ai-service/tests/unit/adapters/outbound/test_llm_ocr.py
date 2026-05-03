import pytest

import app.adapters.outbound.llm_ocr as llm_ocr


@pytest.mark.parametrize(
    "raw,expected_snippets",
    [
        (
            "Email: a.b+1@test.com",
            ["[REDACTED_EMAIL]"],
        ),
        (
            "Phone: 123-456-7890 and 123 456 7890 and 123.456.7890",
            ["[REDACTED_PHONE]"],
        ),
        (
            "Card: 4242 4242 4242 4242 and 4242-4242-4242-4242",
            ["[REDACTED_CREDIT_CARD]"],
        ),
        (
            "IP: 192.168.0.1",
            ["[REDACTED_IP_ADDRESS]"],
        ),
    ],
)
def test_redact_sensitive_redacts_expected_patterns(raw, expected_snippets):
    """Verify `redact_sensitive` replaces PII patterns with deterministic tokens."""
    redacted = llm_ocr.redact_sensitive(raw)
    for snippet in expected_snippets:
        assert snippet in redacted
    assert "test.com" not in redacted or "[REDACTED_EMAIL]" in redacted


@pytest.mark.asyncio
async def test_llm_ocr_adapter_analyze_diagram_redacts_agent_output(tmp_path, monkeypatch):
    """Ensure `LlmOCRAdapter.analyze_diagram` calls the Strands Agent and redacts its output."""
    # Avoid real client construction / settings dependency.
    monkeypatch.setattr(llm_ocr, "build_llm_client", lambda **kwargs: object())

    captured = {"blocks": None}

    class FakeAgent:
        def __init__(self, name, system_prompt, model):
            assert name == "extractor"
            assert system_prompt == llm_ocr.SYSTEM_PROMPT
            assert model is not None

        def __call__(self, blocks):
            captured["blocks"] = blocks
            # Include a few sensitive tokens to prove redaction.
            return "contact me at a.b@test.com or 123-456-7890 from 10.0.0.1"

    monkeypatch.setattr(llm_ocr, "Agent", FakeAgent)

    # Create a minimal file to exercise file_to_content_blocks() without external IO.
    p = tmp_path / "diagram.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    adapter = llm_ocr.LlmOCRAdapter()
    out = await adapter.analyze_diagram(str(p))

    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_PHONE]" in out
    assert "[REDACTED_IP_ADDRESS]" in out
    assert "a.b@test.com" not in out

    # Also assert content blocks were built/passed.
    assert isinstance(captured["blocks"], list)
    assert any(isinstance(b, dict) and "image" in b for b in captured["blocks"])

