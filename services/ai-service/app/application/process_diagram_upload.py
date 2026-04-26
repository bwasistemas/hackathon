"""Use case: OCR → LLM analysis → persist upload result (RabbitMQ-driven flow)."""
import json
import os
import magic
from typing import Optional

from app.application.ports import LlmAnalyzerPort, TextExtractionPort, UploadRepositoryPort
from app.domain.models import AnalysisResult

from app.adapters.outbound.llm_ocr import LlmOCRAdapter


class ProcessDiagramUploadUseCase:
    """Use case: OCR → LLM analysis → persist upload result (RabbitMQ-driven flow)."""
    ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

    def __init__(
        self,
        ocr: LlmOCRAdapter,
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

            # Validate file
            self._validate_file(local_file_path)

            text = await self._ocr.analyze_diagram(local_file_path)
            source_hint = _build_source_hint(local_file_path)

            try:
                result = await self._llm.analyze(text, source_hint=source_hint)
                ai_result = _analysis_to_storage_dict(result)
            except Exception as e:
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

    def _validate_file(self, file_path: str) -> None:
        # Validate extension
        if not any(file_path.lower().endswith(ext) for ext in self.ALLOWED_EXTENSIONS):
            raise ValueError(f"Unsupported file type. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}")
        
        # Validate size
        if os.path.getsize(file_path) > self.MAX_FILE_SIZE:
            raise ValueError(f"File too large: {os.path.getsize(file_path)} bytes > {self.MAX_FILE_SIZE}")
        
        # Validate MIME type
        mime = magic.Magic(mime=True)
        actual_mime = mime.from_file(file_path)
        allowed_mimes = ['application/pdf', 'image/png', 'image/jpeg', 'image/bmp', 'image/gif', 'image/webp']
        if actual_mime not in allowed_mimes:
            raise ValueError(f"Invalid file type: {actual_mime}")


def _build_source_hint(file_path: str) -> str:
    path_lower = file_path.lower()
    if path_lower.endswith(".pdf"):
        return "PDF with architecture diagram pages"
    if path_lower.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp")):
        return "Image file containing an architecture diagram"
    return f"File path or source: {file_path}"


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
