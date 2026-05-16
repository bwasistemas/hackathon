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
    """LlmOCRAdapter.analyze_diagram runs vision OCR and redacts PII from the output."""
    from pydantic import SecretStr
    from app.config import Settings

    fake_settings = Settings(
        openai_api_key=SecretStr("fake-key"),
        openai_base_url="http://fake",
        llm_model="fake-model",
        llm_ocr="fake-ocr-model",
        database_url="",
        rabbitmq_host="localhost",
        rabbitmq_port=5672,
        rabbitmq_user="user",
        rabbitmq_password=SecretStr("pass"),
        minio_endpoint="localhost:9000",
        minio_access_key="user",
        minio_secret_key=SecretStr("pass1234"),
        minio_bucket="bucket",
        minio_region="us-east-1",
        minio_use_ssl=False,
        max_handoffs=20,
        max_iterations=20,
        execution_timeout=60.0,
        node_timeout=30.0,
        repetitive_handoff_detection_window=8,
        repetitive_handoff_min_unique_agents=3,
        jwt_secret_key=SecretStr("a" * 32),
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
    )

    # build_llm_client returns a non-None object so the vision path is taken.
    monkeypatch.setattr(llm_ocr, "build_llm_client", lambda **kwargs: object())
    # Patch the sync extraction to return text with PII without real IO.
    monkeypatch.setattr(
        llm_ocr,
        "_extract_with_vision_sync",
        lambda client, path: "contact me at a.b@test.com or 123-456-7890 from 10.0.0.1",
    )

    p = tmp_path / "diagram.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    adapter = llm_ocr.LlmOCRAdapter(settings=fake_settings)
    out = await adapter.analyze_diagram(str(p))

    assert "[REDACTED_EMAIL]" in out.text
    assert "[REDACTED_PHONE]" in out.text
    assert "[REDACTED_IP_ADDRESS]" in out.text
    assert "a.b@test.com" not in out.text

