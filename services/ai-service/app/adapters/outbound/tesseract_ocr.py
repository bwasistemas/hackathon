"""OCR extraction using Pillow, pytesseract, and optional pdf2image for PDFs."""
import asyncio

from app.application.ports import TextExtractionPort


class TesseractTextExtractor(TextExtractionPort):
    async def extract_text(self, file_path: str) -> str:
        path_lower = file_path.lower()
        try:
            if path_lower.endswith(".pdf"):
                return await _extract_from_pdf(file_path)
            return await _extract_from_image(file_path)
        except Exception as e:
            return f"OCR Error: {e}"


async def _extract_from_pdf(file_path: str) -> str:
    from pdf2image import convert_from_path

    images = await asyncio.to_thread(convert_from_path, file_path)
    import pytesseract

    text_chunks: list[str] = []
    for img in images:
        extracted = await asyncio.to_thread(pytesseract.image_to_string, img)
        if extracted:
            text_chunks.append(extracted.strip())

    text = "\n".join(text_chunks).strip()
    header = f"[PDF Diagram: {len(images)} page(s)]\n\n"
    body = text if text else "No text found in PDF image(s). Use the diagram visual content and labels to infer architecture."
    return f"{header}{body}"


async def _extract_from_image(file_path: str) -> str:
    from PIL import Image
    import pytesseract

    img = await asyncio.to_thread(Image.open, file_path)
    extracted_text = await asyncio.to_thread(pytesseract.image_to_string, img)
    body = extracted_text.strip() if extracted_text else "No text found in image. Use the diagram visual content and labels to infer architecture."
    return f"[Image Diagram]\n\n{body}"
