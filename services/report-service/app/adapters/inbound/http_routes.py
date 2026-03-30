"""FastAPI inbound adapter: maps HTTP <-> application use cases."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query

from app.adapters.inbound.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    ReportResponse,
    ReportSummarySchema,
    StatisticsResponse,
)
from app.application.report_management import (
    GetReportUseCase,
    ListReportsUseCase,
    SubmitFeedbackUseCase,
    GetStatisticsUseCase,
)
from app.domain.exceptions import (
    ReportNotFoundError,
    InvalidRatingError,
    UploadNotFoundError,
    DatabaseError,
)


def get_get_report_use_case(request: Request) -> GetReportUseCase:
    """Dependency injection for get report use case."""
    return request.app.state.get_report_use_case


def get_list_reports_use_case(request: Request) -> ListReportsUseCase:
    """Dependency injection for list reports use case."""
    return request.app.state.list_reports_use_case


def get_submit_feedback_use_case(request: Request) -> SubmitFeedbackUseCase:
    """Dependency injection for submit feedback use case."""
    return request.app.state.submit_feedback_use_case


def get_statistics_use_case(request: Request) -> GetStatisticsUseCase:
    """Dependency injection for statistics use case."""
    return request.app.state.get_statistics_use_case


def build_router() -> APIRouter:
    """Build and configure the HTTP router."""
    router = APIRouter()

    @router.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "service": "report-service"}

    @router.get("/health/db")
    async def health_db(request: Request):
        """Database health check endpoint."""
        try:
            if request.app.state.db_pool:
                async with request.app.state.db_pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                return {"status": "online"}
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Database Offline")

    @router.get("/reports/{upload_id}", response_model=ReportResponse)
    async def get_report(
        upload_id: str,
        use_case: GetReportUseCase = Depends(get_get_report_use_case),
    ):
        """Get report details by upload ID."""
        try:
            report = await use_case.execute(upload_id)
            return ReportResponse(
                id=report.id,
                filename=report.filename,
                status=report.status,
                analysis=report.analysis,
                created_at=report.created_at.isoformat(),
            )
        except ReportNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except DatabaseError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/reports", response_model=list[ReportSummarySchema])
    async def list_reports(
        status: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=100),
        use_case: ListReportsUseCase = Depends(get_list_reports_use_case),
    ):
        """List reports with optional status filter."""
        try:
            reports = await use_case.execute(status, limit)
            return [
                ReportSummarySchema(
                    id=r.id,
                    filename=r.filename,
                    status=r.status,
                    created_at=r.created_at.isoformat(),
                )
                for r in reports
            ]
        except DatabaseError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/feedback", response_model=FeedbackResponse)
    async def submit_feedback(
        feedback: FeedbackRequest,
        use_case: SubmitFeedbackUseCase = Depends(get_submit_feedback_use_case),
    ):
        """Submit feedback for a report."""
        try:
            await use_case.execute(
                feedback.upload_id,
                feedback.rating,
                feedback.comment,
            )
            return FeedbackResponse(
                message="Feedback submitted successfully",
                rating=feedback.rating,
            )
        except InvalidRatingError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except UploadNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except DatabaseError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/stats", response_model=StatisticsResponse)
    async def get_stats(
        use_case: GetStatisticsUseCase = Depends(get_statistics_use_case),
    ):
        """Get statistics about uploads and feedback."""
        try:
            stats = await use_case.execute()
            return StatisticsResponse(
                total_uploads=stats.total_uploads,
                by_status=stats.by_status,
                avg_rating=stats.avg_rating,
                total_feedback=stats.total_feedback,
            )
        except DatabaseError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
