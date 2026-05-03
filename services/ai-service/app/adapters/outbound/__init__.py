"""
Outbound adapters package.

Keep this module import-light.

Some outbound adapters depend on optional heavy/IO libraries (DB drivers, OCR, etc.).
Importing them eagerly here makes any import of `app.adapters.outbound` fail if an
optional dependency isn't installed, and slows down startup. Prefer lazy imports.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "AsyncpgUploadRepository",
    "MinIOStorage",
    "NullUploadRepository",
    "OpenAiLlmAdapter",
    "TesseractTextExtractor",
    "build_openai_client",
    "create_upload_repository",
]


_EXPORTS: dict[str, tuple[str, str]] = {
    "AsyncpgUploadRepository": ("app.adapters.outbound.asyncpg_uploads", "AsyncpgUploadRepository"),
    "NullUploadRepository": ("app.adapters.outbound.asyncpg_uploads", "NullUploadRepository"),
    "create_upload_repository": ("app.adapters.outbound.asyncpg_uploads", "create_upload_repository"),
    "MinIOStorage": ("app.adapters.outbound.minio_storage", "MinIOStorage"),
    "OpenAiLlmAdapter": ("app.adapters.outbound.openai_adapter", "OpenAiLlmAdapter"),
    "build_openai_client": ("app.adapters.outbound.openai_adapter", "build_openai_client"),
    "TesseractTextExtractor": ("app.adapters.outbound.tesseract_ocr", "TesseractTextExtractor"),
}


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if not target:
        raise AttributeError(name)
    mod_name, attr = target
    mod = import_module(mod_name)
    value = getattr(mod, attr)
    globals()[name] = value
    return value
