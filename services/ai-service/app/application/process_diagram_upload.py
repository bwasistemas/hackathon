"""Use case: OCR → LLM analysis → persist upload result (RabbitMQ-driven flow)."""
import json
import os
from typing import Optional

from app.application.ports import LlmAnalyzerPort, TextExtractionPort, UploadRepositoryPort
from app.domain.models import AnalysisResult


class ProcessDiagramUploadUseCase:
    """Use case: OCR → LLM analysis → persist upload result (RabbitMQ-driven flow)."""
    def __init__(
        self,
        ocr: TextExtractionPort,
        llm: LlmAnalyzerPort,
        uploads: UploadRepositoryPort,
        storage: Optional[object] = None,
    ) -> None:
        self._ocr = ocr
        self._llm = llm
        self._uploads = uploads
        self._storage = storage

    async def execute(self, upload_id: str, file_path: str) -> None:
        uid = str(upload_id)
        await self._uploads.mark_processing(uid)

        local_file_path = file_path
        temp_file_to_cleanup = None
        
        try:
            # If file is in MinIO, download it first
            if file_path.startswith("minio://") and self._storage:
                local_file_path = await self._storage.download_file(file_path)
                temp_file_to_cleanup = local_file_path
                print(f"Downloaded from MinIO: {file_path} -> {local_file_path}")
            
            text = await self._ocr.extract_text(local_file_path)

            try:
                result = await self._llm.analyze(text)
                print("===== AQUI OW ====", result)
                ai_result = _analysis_to_storage_dict(result)
            except Exception as e:
                print("==== oi =====", result)
                ai_result = {"error": str(e)}

            payload = json.dumps({"text": text, "ai": ai_result})
            await self._uploads.mark_done_with_payload(uid, payload)
        
        finally:
            # Clean up temp file if we downloaded from MinIO
            if temp_file_to_cleanup and os.path.exists(temp_file_to_cleanup):
                try:
                    os.unlink(temp_file_to_cleanup)
                except Exception as e:
                    print(f"Failed to cleanup temp file {temp_file_to_cleanup}: {e}")


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
