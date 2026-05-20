"""Inbound/outbound ports (interfaces) — the application depends on these, not on adapters."""
from typing import Protocol, Optional, List

from app.domain.models import Report, ReportSummary, Statistics


class ReportRepositoryPort(Protocol):
    """Port for report retrieval operations — implemented by HttpUploadClientAdapter."""

    async def get_report(self, upload_id: str) -> Optional[Report]:
        """Retrieve a report by upload ID via upload-service HTTP API."""
        ...

    async def list_reports(self, status: Optional[str], limit: int) -> List[ReportSummary]:
        """List reports with optional status filter via upload-service HTTP API."""
        ...

    async def check_upload_exists(self, upload_id: str) -> bool:
        """Check if upload exists via upload-service HTTP API."""
        ...

    async def get_upload_counts(self) -> dict:
        """Return {total, by_status} from upload-service /stats/uploads endpoint."""
        ...


class FeedbackRepositoryPort(Protocol):
    """Port for feedback operations — implemented by AsyncpgFeedbackRepository."""

    async def create_feedback(self, upload_id: str, rating: int, comment: Optional[str]) -> None:
        """Create feedback for an upload."""
        ...

    async def get_feedback_stats(self) -> dict:
        """Return {avg_rating: float, total_feedback: int} from feedback table."""
        ...
