"""Inbound/outbound ports (interfaces) — the application depends on these, not on adapters."""
from typing import Protocol, Optional, List

from app.domain.models import Report, ReportSummary, Feedback, Statistics


class ReportRepositoryPort(Protocol):
    """Port for report retrieval operations."""
    async def get_report(self, upload_id: str) -> Optional[Report]:
        """Retrieve a report by upload ID."""
        ...

    async def list_reports(self, status: Optional[str], limit: int) -> List[ReportSummary]:
        """List reports with optional status filter."""
        ...

    async def check_upload_exists(self, upload_id: str) -> bool:
        """Check if upload exists."""
        ...


class FeedbackRepositoryPort(Protocol):
    """Port for feedback operations."""
    async def create_feedback(self, upload_id: str, rating: int, comment: Optional[str]) -> None:
        """Create feedback for an upload."""
        ...

    async def get_statistics(self) -> Statistics:
        """Get statistics about uploads and feedback."""
        ...
