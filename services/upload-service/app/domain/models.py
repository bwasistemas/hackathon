"""Core domain models for upload management."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Upload:
    """Upload entity representing a file upload."""
    id: str
    filename: str
    content_type: str
    file_size: int
    status: str
    file_path: str
    created_at: datetime
    updated_at: datetime
    minio_url: Optional[str] = None


@dataclass(frozen=True)
class UploadResult:
    """Result of a file upload operation."""
    id: str
    filename: str
    status: str
    message: str
    minio_url: Optional[str] = None
