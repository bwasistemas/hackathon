"""Use case: OCR → LLM analysis → persist upload result (RabbitMQ-driven flow)."""
import json

from app.application.ports import LlmAnalyzerPort, TextExtractionPort, UploadRepositoryPort
from app.domain.models import AnalysisResult


class ProcessDiagramUploadUseCase:
    """Use case: OCR → LLM analysis → persist upload result (RabbitMQ-driven flow)."""
    def __init__(
        self,
        ocr: TextExtractionPort,
        llm: LlmAnalyzerPort,
        uploads: UploadRepositoryPort,
    ) -> None:
        self._ocr = ocr
        self._llm = llm
        self._uploads = uploads

    async def execute(self, upload_id: str, file_path: str) -> None:
        uid = str(upload_id)
        await self._uploads.mark_processing(uid)

        text = await self._ocr.extract_text(file_path)

        try:
            result = await self._llm.analyze(text)
            ai_result = _analysis_to_storage_dict(result)
        except Exception as e:
            ai_result = {"error": str(e)}

        payload = json.dumps({"text": text, "ai": ai_result})
        await self._uploads.mark_done_with_payload(uid, payload)


def _analysis_to_storage_dict(result: AnalysisResult) -> dict:
    """Convert an analysis result to a dictionary for storage."""
    return {
        "components": [
            {
                "name": c.name,
                "type": c.component_type,
                "description": c.description,
            }
            for c in result.components
        ],
        "risks": [
            {
                "severity": r.severity,
                "description": r.description,
                "recommendation": r.recommendation,
            }
            for r in result.risks
        ],
        "summary": result.summary,
    }
