"""Inbound/outbound ports (interfaces) — the application depends on these, not on adapters."""
from typing import Protocol

from app.domain.models import AnalysisResult


class LlmAnalyzerPort(Protocol):
    async def analyze(self, text: str) -> AnalysisResult:
        ...


class TextExtractionPort(Protocol):
    async def extract_text(self, file_path: str) -> str:
        ...


class UploadRepositoryPort(Protocol):
    async def mark_processing(self, upload_id: str) -> None:
        ...

    async def mark_done_with_payload(self, upload_id: str, payload_json: str) -> None:
        """Persist completion; payload_json is the serialized file_path column value."""
