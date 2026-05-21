"""Composition root: wires adapters to use cases and builds the FastAPI application."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.adapters.inbound.http_routes import build_router
from app.adapters.outbound.asyncpg_reports import create_feedback_repository
from app.adapters.outbound.http_upload_client import HttpUploadClientAdapter
from app.adapters.outbound.minio_storage import MinIOStorage
from app.application.report_management import (
    GetReportUseCase,
    ListReportsUseCase,
    SubmitFeedbackUseCase,
    GetStatisticsUseCase,
)
from app.config import load_settings
from app.logging_config import setup_logging


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = load_settings()

    setup_logging("report-service")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        feedback_repo, db_pool = await create_feedback_repository(settings.database_url)
        app.state.db_pool = db_pool
        app.state.minio_storage = MinIOStorage(settings)

        report_repo = HttpUploadClientAdapter(
            base_url=settings.upload_service_url,
            username=settings.upload_service_user,
            password=settings.upload_service_password,
        )

        app.state.get_report_use_case = GetReportUseCase(repository=report_repo)
        app.state.list_reports_use_case = ListReportsUseCase(repository=report_repo)
        app.state.submit_feedback_use_case = SubmitFeedbackUseCase(
            feedback_repository=feedback_repo,
            report_repository=report_repo,
        )
        app.state.get_statistics_use_case = GetStatisticsUseCase(
            report_repository=report_repo,
            feedback_repository=feedback_repo,
        )

        yield

        if db_pool:
            await db_pool.close()

    app = FastAPI(
        title="Report Service",
        description="API for retrieving analysis reports and feedback",
        version="1.0.0",
        lifespan=lifespan,
    )

    Instrumentator().instrument(app).expose(app)

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
        status_code=429, content={"detail": "Rate limit exceeded"}
    ))
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(SecurityHeadersMiddleware)

    raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8051")
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    if "*" in allowed_origins:
        allowed_origins = ["http://localhost:8051"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

    app.include_router(build_router(limiter))

    return app
