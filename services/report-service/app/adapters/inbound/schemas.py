"""HTTP request/response DTOs (adapter layer)."""
from typing import Optional

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    """Request schema for submitting feedback."""
    upload_id: str
    rating: int = Field(ge=1, le=5, description="Rating between 1 and 5")
    comment: Optional[str] = None


class ReportResponse(BaseModel):
    """Response schema for report details."""
    id: str
    filename: str
    status: str
    analysis: dict
    created_at: str
    minio_url: Optional[str] = None
    content_type: Optional[str] = None


class ReportSummarySchema(BaseModel):
    """Schema for report summary in list views."""
    id: str
    filename: str
    status: str
    created_at: str


class StatisticsResponse(BaseModel):
    """Response schema for statistics."""
    total_uploads: int
    by_status: dict
    avg_rating: float
    total_feedback: int


class FeedbackResponse(BaseModel):
    """Response schema for feedback submission."""
    message: str
    rating: int
