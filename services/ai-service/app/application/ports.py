"""Inbound/outbound ports (interfaces) — the application depends on these, not on adapters."""
from typing import Protocol

from app.domain.models import AnalysisResult


class LlmAnalyzerPort(Protocol):
    async def analyze(self, text: str, source_hint: str | None = None) -> AnalysisResult:
        ...


class TextExtractionPort(Protocol):
    async def extract_text(self, file_path: str) -> str:
        ...


class ResultPublisherPort(Protocol):
    """Outbound port: publishes analysis result events to diagram.result queue."""

    async def publish_processing(self, upload_id: str) -> None:
        ...

    async def publish_done(self, upload_id: str, payload_json: str) -> None:
        ...

    async def publish_failed(self, upload_id: str, error_message: str) -> None:
        ...
