"""Use case: analyze diagram text with the configured LLM."""
from app.application.ports import LlmAnalyzerPort
from app.domain.models import AnalysisResult


class AnalyzeDiagramUseCase:
    def __init__(self, llm: LlmAnalyzerPort) -> None:
        self._llm = llm

    async def execute(self, text: str) -> AnalysisResult:
        return await self._llm.analyze(text)
