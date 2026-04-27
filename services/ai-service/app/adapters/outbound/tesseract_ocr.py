"""OCR extraction using Pillow, pytesseract, and optional pdf2image for PDFs."""
import asyncio
import os
from typing import Optional

from app.application.ports import TextExtractionPort


class TesseractTextExtractor(TextExtractionPort):
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    MAX_IMAGE_DIMENSION = 8000  # pixels
    OCR_TIMEOUT = 60  # seconds per page
    MAX_PDF_PAGES = 100
    ALLOWED_BASEDIR = "/tmp"  # Or configurable

    async def extract_text(self, file_path: str) -> str:
        # 1. Path validation (prevent directory traversal)
        file_path = os.path.abspath(file_path)
        if not file_path.startswith(self.ALLOWED_BASEDIR):
            raise ValueError("Path traversal detected")
        
        # 2. File existence and size check
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        if os.path.getsize(file_path) > self.MAX_FILE_SIZE:
            raise ValueError(f"File too large: {os.path.getsize(file_path)} bytes")
        
        path_lower = file_path.lower()
        try:
            if path_lower.endswith(".pdf"):
                return await self._extract_from_pdf_safe(file_path)
            return await self._extract_from_image_safe(file_path)
        except asyncio.TimeoutError:
            return "OCR Error: Processing timeout (file too complex)"
        except Exception as e:
            # Log but don't expose full error to LLM
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"OCR extraction failed: {e}", exc_info=True)
            return "OCR Error: Could not extract text from file"
    
    async def _extract_from_pdf_safe(self, file_path: str) -> str:
        from pdf2image import convert_from_path
        
        try:
            # 1. Count pages first (without converting)
            from PyPDF2 import PdfReader
            with open(file_path, 'rb') as f:
                pdf_reader = PdfReader(f)
                num_pages = len(pdf_reader.pages)
            
            if num_pages > self.MAX_PDF_PAGES:
                return f"PDF Error: Too many pages ({num_pages} > {self.MAX_PDF_PAGES})"
            
            # 2. Convert with timeout
            images = await asyncio.wait_for(
                asyncio.to_thread(convert_from_path, file_path),
                timeout=self.OCR_TIMEOUT * num_pages
            )
            
            import pytesseract
            text_chunks = []
            for idx, img in enumerate(images):
                try:
                    # Validate image dimensions
                    if max(img.size) > self.MAX_IMAGE_DIMENSION:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Image {idx} exceeds max dimension")
                        img.thumbnail((self.MAX_IMAGE_DIMENSION, self.MAX_IMAGE_DIMENSION))
                    
                    extracted = await asyncio.wait_for(
                        asyncio.to_thread(pytesseract.image_to_string, img),
                        timeout=self.OCR_TIMEOUT
                    )
                    if extracted:
                        text_chunks.append(extracted.strip())
                except asyncio.TimeoutError:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"OCR timeout on page {idx}")
                    continue
            
            text = "\n".join(text_chunks).strip()
            if not text:
                return "[PDF] No text extracted"
            return f"[PDF: {len(images)} pages]\n\n{text}"
        
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"PDF extraction error: {e}")
            return "OCR Error: Failed to process PDF"
    
    async def _extract_from_image_safe(self, file_path: str) -> str:
        from PIL import Image
        import pytesseract
        
        try:
            img = await asyncio.wait_for(
                asyncio.to_thread(Image.open, file_path),
                timeout=self.OCR_TIMEOUT
            )
            
            # Validate image dimensions
            if max(img.size) > self.MAX_IMAGE_DIMENSION:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Resizing image from {img.size}")
                img.thumbnail((self.MAX_IMAGE_DIMENSION, self.MAX_IMAGE_DIMENSION))
            
            extracted_text = await asyncio.wait_for(
                asyncio.to_thread(pytesseract.image_to_string, img),
                timeout=self.OCR_TIMEOUT
            )
            
            body = extracted_text.strip() if extracted_text else "[Image] No text found"
            return f"[Image]\n\n{body}"
        
        except asyncio.TimeoutError:
            return "OCR Error: Image processing timeout"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Image extraction error: {e}")
            return "OCR Error: Failed to process image"
