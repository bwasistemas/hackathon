"""Composition root: wires adapters to use cases and builds the FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.adapters.inbound.http_routes import build_router
from app.adapters.outbound.asyncpg_reports import create_repositories
from app.adapters.outbound.minio_storage import MinIOStorage
from app.application.report_management import (
    GetReportUseCase,
    ListReportsUseCase,
    SubmitFeedbackUseCase,
    GetStatisticsUseCase,
)
from app.config import load_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifecycle and dependency injection."""
        report_repo, feedback_repo, db_pool = await create_repositories(
            settings.database_url
        )
        app.state.db_pool = db_pool
        app.state.minio_storage = MinIOStorage(settings)

        app.state.get_report_use_case = GetReportUseCase(repository=report_repo)
        app.state.list_reports_use_case = ListReportsUseCase(repository=report_repo)
        app.state.submit_feedback_use_case = SubmitFeedbackUseCase(
            feedback_repository=feedback_repo,
            report_repository=report_repo,
        )
        app.state.get_statistics_use_case = GetStatisticsUseCase(
            repository=feedback_repo
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_router())

    return app
