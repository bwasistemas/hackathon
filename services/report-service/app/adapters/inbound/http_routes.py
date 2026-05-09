"""FastAPI inbound adapter: maps HTTP <-> application use cases."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address
import os
from fastapi.responses import Response

from app.adapters.inbound.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    ReportResponse,
    ReportSummarySchema,
    StatisticsResponse,
)
from app.adapters.helpers.auth import verify_token
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

logger = logging.getLogger(__name__)

# OAuth2 scheme: this service does NOT issue tokens, it only validates them.
# Clients must obtain tokens from the upload-service `/token` endpoint, which is
# the single source of authentication for the platform.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/upload-service/token", auto_error=True)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


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


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate the bearer token (issued by upload-service) and return the username."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = verify_token(token, credentials_exception)
    return token_data.username


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
    @limiter.limit("10/minute")
    async def get_report(
        request: Request,
        upload_id: str,
        current_user: str = Depends(get_current_user),
        use_case: GetReportUseCase = Depends(get_get_report_use_case),
    ):
        """Get report details by upload ID."""
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"Report access by user {current_user} from {client_ip}: {upload_id}")
        
        try:
            report = await use_case.execute(upload_id)
            return ReportResponse(
                id=report.id,
                filename=report.filename,
                status=report.status,
                analysis=report.analysis,
                created_at=report.created_at.isoformat(),
                minio_url=report.minio_url,
                content_type=report.content_type,
            )
        except ReportNotFoundError as e:
            logger.warning(f"Report not found: {upload_id} by user {current_user}")
            raise HTTPException(status_code=404, detail=str(e)) from e
        except DatabaseError as e:
            logger.error(f"Database error accessing report {upload_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error accessing report {upload_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/reports/{upload_id}/attachment")
    async def get_attachment(
        upload_id: str,
        request: Request,
        use_case: GetReportUseCase = Depends(get_get_report_use_case),
    ):
        """Stream the original uploaded file from MinIO."""
        minio_storage = getattr(request.app.state, "minio_storage", None)
        if not minio_storage:
            raise HTTPException(status_code=503, detail="Storage unavailable")
        try:
            report = await use_case.execute(upload_id)
            if not report.minio_url:
                raise HTTPException(status_code=404, detail="No attachment")
            file_path = await minio_storage.download_file(report.minio_url)
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
            finally:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            content_type = report.content_type or "application/octet-stream"
            return Response(content=data, media_type=content_type)
        except HTTPException:
            raise
        except ReportNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/reports", response_model=list[ReportSummarySchema])
    async def list_reports(
        status: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=100),
        current_user: str = Depends(get_current_user),
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
        current_user: str = Depends(get_current_user),
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
        current_user: str = Depends(get_current_user),
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
