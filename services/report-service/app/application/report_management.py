"""Use cases for report management."""
from typing import Optional, List

from app.application.ports import ReportRepositoryPort, FeedbackRepositoryPort
from app.domain.exceptions import ReportNotFoundError, InvalidRatingError, UploadNotFoundError
from app.domain.models import Report, ReportSummary, Statistics


class GetReportUseCase:
    """Use case: get report details by upload ID."""
    
    def __init__(self, repository: ReportRepositoryPort) -> None:
        self._repository = repository
    
    async def execute(self, upload_id: str) -> Report:
        """Get report by upload ID."""
        report = await self._repository.get_report(upload_id)
        if not report:
            raise ReportNotFoundError(f"Report not found for upload ID: {upload_id}")
        return report


class ListReportsUseCase:
    """Use case: list reports with optional filtering."""
    
    def __init__(self, repository: ReportRepositoryPort) -> None:
        self._repository = repository
    
    async def execute(self, status: Optional[str] = None, limit: int = 50) -> List[ReportSummary]:
        """List reports with optional status filter."""
        return await self._repository.list_reports(status, limit)


class SubmitFeedbackUseCase:
    """Use case: submit feedback for a report."""
    
    def __init__(
        self,
        feedback_repository: FeedbackRepositoryPort,
        report_repository: ReportRepositoryPort,
    ) -> None:
        self._feedback_repository = feedback_repository
        self._report_repository = report_repository
    
    async def execute(self, upload_id: str, rating: int, comment: Optional[str] = None) -> None:
        """Submit feedback for an upload."""
        if not 1 <= rating <= 5:
            raise InvalidRatingError("Rating must be between 1 and 5")
        
        upload_exists = await self._report_repository.check_upload_exists(upload_id)
        if not upload_exists:
            raise UploadNotFoundError(f"Upload not found: {upload_id}")
        
        await self._feedback_repository.create_feedback(upload_id, rating, comment)


class GetStatisticsUseCase:
    """Use case: get statistics about uploads and feedback."""
    
    def __init__(self, repository: FeedbackRepositoryPort) -> None:
        self._repository = repository
    
    async def execute(self) -> Statistics:
        """Get statistics."""
        return await self._repository.get_statistics()
