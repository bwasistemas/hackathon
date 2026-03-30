"""HTTP request/response DTOs (adapter layer)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UploadResponse(BaseModel):
    """Response schema for upload operations."""
    id: str
    filename: str
    status: str
    message: str
    minio_url: Optional[str] = None


class UploadListItemSchema(BaseModel):
    """Schema for upload list item."""
    id: str
    filename: str
    status: str
    created_at: datetime
    minio_url: Optional[str] = None


class UploadDetailSchema(BaseModel):
    """Schema for upload detail."""
    id: str
    filename: str
    content_type: str
    file_size: int
    status: str
    file_path: str
    minio_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
