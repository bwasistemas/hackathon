"""Diagram text extraction: multimodal LLM (LLM_OCR model) with Tesseract fallback."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import shutil
import tempfile
from typing import Any, Optional

from PIL import Image

from app.adapters.outbound.helpers.llm import OpenAIClient, build_llm_client, normalize_assistant_content
from app.adapters.outbound.tesseract_ocr import TesseractTextExtractor, is_under_system_temp_dir
from app.config import Settings, load_settings
from app.domain.models import DiagramTextExtraction

logger = logging.getLogger(__name__)

MAX_VISION_PDF_PAGES = max(1, int(os.getenv("LLM_OCR_MAX_PDF_PAGES", "15")))
LLM_OCR_MAX_TOKENS = max(512, int(os.getenv("LLM_OCR_MAX_TOKENS", "4096")))
VISION_IMAGE_MAX_SIDE = max(512, int(os.getenv("LLM_OCR_IMAGE_MAX_SIDE", "2048")))
_FORCE_TESSERACT = os.getenv("LLM_OCR_DISABLE", "").lower() in ("1", "true", "yes", "on")

VISION_PROMPT_PT = """Analise esta imagem ou páginas de diagrama de arquitetura de software.

Extraia e liste em texto corrido (português do Brasil):
1) Todas as etiquetas, títulos e anotações legíveis.
2) Nomes de componentes, serviços, APIs, bases de dados e filas visíveis.
3) Relações indicadas por setas ou linhas (quem liga a quem), quando dedutível.
4) Legendas ou números que pareçam fluxos ou etapas.

Se houver pouco texto mas formas claras, descreva brevemente o layout (camadas, agrupamentos).
Não invente nomes ilegíveis; indique [ilegível] quando aplicável.
Responda apenas com o texto útil para um arquiteto revisar — sem JSON e sem markdown."""


def _response_text(response: Any) -> str:
    if hasattr(response, "choices") and response.choices:
        msg = response.choices[0].message
        raw = getattr(msg, "content", None)
        text = normalize_assistant_content(raw)
        if text:
            return text
    if isinstance(response, dict):
        choices = response.get("choices")
        if choices and isinstance(choices, list):
            message = choices[0].get("message")
            if isinstance(message, dict):
                return normalize_assistant_content(message.get("content"))
    return normalize_assistant_content(str(response))


def _pil_to_jpeg_data_url(img: Image.Image, max_side: int) -> str:
    rgb = img.convert("RGB")
    w, h = rgb.size
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        rgb = rgb.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=85, optimize=True)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _build_vision_user_content(file_path: str) -> list[dict[str, Any]]:
    path_lower = file_path.lower()
    content: list[dict[str, Any]] = [{"type": "text", "text": VISION_PROMPT_PT}]

    if path_lower.endswith(".pdf"):
        from PyPDF2 import PdfReader
        from pdf2image import convert_from_path

        with open(file_path, "rb") as f:
            num_pages = len(PdfReader(f).pages)
        last_page = min(num_pages, MAX_VISION_PDF_PAGES)
        if num_pages > MAX_VISION_PDF_PAGES:
            logger.warning(
                "PDF has %s pages; vision OCR uses first %s only",
                num_pages,
                MAX_VISION_PDF_PAGES,
            )
        dpi = int(os.getenv("LLM_OCR_PDF_DPI", "150"))
        images = convert_from_path(file_path, first_page=1, last_page=last_page, dpi=dpi)
        for idx, pil_img in enumerate(images):
            try:
                url = _pil_to_jpeg_data_url(pil_img, VISION_IMAGE_MAX_SIDE)
                content.append({"type": "image_url", "image_url": {"url": url}})
            except Exception as e:
                logger.warning("Vision OCR: failed to encode PDF page %s: %s", idx, e)
        if len(content) <= 1:
            raise ValueError("No PDF pages could be encoded for vision OCR")
        return content

    rgb = Image.open(file_path)
    try:
        url = _pil_to_jpeg_data_url(rgb, VISION_IMAGE_MAX_SIDE)
    finally:
        rgb.close()
    content.append({"type": "image_url", "image_url": {"url": url}})
    return content


def _extract_with_vision_sync(client: OpenAIClient, file_path: str) -> str:
    model = client.model_id
    if not model:
        raise ValueError("Vision OCR requires LLM_OCR / model_id on the client")
    user_content = _build_vision_user_content(file_path)
    resp = client.create_chat_completion(
        model=model,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=LLM_OCR_MAX_TOKENS,
        temperature=0.0,
    )
    return _response_text(resp)


class LlmOCRAdapter:
    """Prefer multimodal LLM (settings.llm_ocr); fall back to Tesseract if disabled or on error."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or load_settings()
        self._tesseract = TesseractTextExtractor()
        self._vision_client: Optional[OpenAIClient] = None
        if not _FORCE_TESSERACT:
            self._vision_client = build_llm_client(
                api_key=self._settings.openai_api_key.get_secret_value(),
                base_url=self._settings.openai_base_url,
                model_id=self._settings.llm_ocr,
                max_tokens=LLM_OCR_MAX_TOKENS,
                temperature=0.0,
            )
            if self._vision_client is None:
                logger.info("Vision OCR skipped: OPENAI_API_KEY not set; using Tesseract only")

    async def analyze_diagram(self, file: str) -> DiagramTextExtraction:
        configured_model = (self._settings.llm_ocr or "").strip() or "(LLM_OCR não definido)"

        if not is_under_system_temp_dir(file):
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file)[1]) as tmp:
                shutil.copyfile(file, tmp.name)
                temp_path = tmp.name
        else:
            temp_path = file

        try:
            if self._vision_client is not None:
                try:
                    logger.info(
                        "Vision OCR: calling model %s for %s",
                        self._settings.llm_ocr,
                        os.path.basename(temp_path),
                    )
                    text = await asyncio.to_thread(_extract_with_vision_sync, self._vision_client, temp_path)
                    if text:
                        logger.info("Vision OCR succeeded (%s chars)", len(text))
                        return DiagramTextExtraction(
                            text=text,
                            source="llm_multimodal",
                            multimodal_model=configured_model,
                            detail_pt=(
                                f"Fonte: modelo multimodal ({configured_model}, variável de ambiente LLM_OCR). "
                                "O texto abaixo foi gerado por esse modelo ao analisar a imagem ou o PDF."
                            ),
                        )
                    logger.warning("Vision OCR returned empty content; falling back to Tesseract")
                    tess_reason = (
                        f"Fonte: OCR local (Tesseract), em fallback porque o modelo multimodal "
                        f"({configured_model}) devolveu conteúdo vazio."
                    )
                except Exception as e:
                    logger.warning(
                        "Vision OCR failed (%s: %s); falling back to Tesseract",
                        type(e).__name__,
                        e,
                        exc_info=True,
                    )
                    tess_reason = (
                        f"Fonte: OCR local (Tesseract), em fallback após falha na chamada ao modelo "
                        f"multimodal ({configured_model}): {type(e).__name__}."
                    )
            else:
                tess_reason = (
                    "Fonte: OCR local (Tesseract). O modelo multimodal não foi chamado "
                    "(OPENAI_API_KEY ausente/inválida ou LLM_OCR_DISABLE=true). "
                    f"Modelo configurado em LLM_OCR para quando a vision estiver ativa: {configured_model}."
                )

            extracted_text = await self._tesseract.extract_text(temp_path)
            if not extracted_text:
                extracted_text = "OCR Error: No text could be extracted from the file."
            return DiagramTextExtraction(
                text=extracted_text,
                source="tesseract",
                multimodal_model=configured_model,
                detail_pt=tess_reason,
            )
        finally:
            if temp_path != file and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
