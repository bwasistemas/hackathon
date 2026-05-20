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
from app.adapters.inbound.rabbitmq_result_consumer import start_diagram_result_consumer
from app.adapters.outbound.asyncpg_uploads import create_upload_repository
from app.adapters.outbound.minio_storage import MinIOStorageAdapter
from app.adapters.outbound.rabbitmq_publisher import RabbitMQPublisher, connect_rabbitmq
from app.application.upload_file import (
    UploadFileUseCase,
    ListUploadsUseCase,
    GetUploadUseCase,
    UpdateUploadResultUseCase,
    GetUploadStatsUseCase,
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
        # Do not send Content-Security-Policy from REST APIs: browsers merge CSP across
        # responses and `default-src 'self'` would block fonts/scripts loaded by the SPA.
        return response


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = load_settings()
    
    # Setup logging
    setup_logging("upload-service")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifecycle and dependency injection."""
        # Create database connection pool and repository
        upload_repo, db_pool = await create_upload_repository(settings.database_url)
        app.state.db_pool = db_pool

        # Create storage adapter
        storage = MinIOStorageAdapter(settings)

        # Connect to RabbitMQ and create publisher
        rabbit_connection = await connect_rabbitmq(
            settings.rabbitmq_host,
            settings.rabbitmq_port,
            settings.rabbitmq_user,
            settings.rabbitmq_password,
        )
        app.state.rabbit_connection = rabbit_connection
        publisher = RabbitMQPublisher(rabbit_connection)

        # Wire use cases with dependencies
        app.state.upload_use_case = UploadFileUseCase(
            storage=storage,
            repository=upload_repo,
            publisher=publisher,
        )
        app.state.list_uploads_use_case = ListUploadsUseCase(
            repository=upload_repo,
        )
        app.state.get_upload_use_case = GetUploadUseCase(
            repository=upload_repo,
        )
        update_result_use_case = UpdateUploadResultUseCase(repository=upload_repo)
        app.state.update_result_use_case = update_result_use_case
        app.state.get_upload_stats_use_case = GetUploadStatsUseCase(repository=upload_repo)

        await start_diagram_result_consumer(rabbit_connection, update_result_use_case)

        yield

        # Cleanup
        if db_pool:
            await db_pool.close()
        if rabbit_connection:
            await rabbit_connection.close()

    app = FastAPI(
        title="Upload Service",
        description="API for uploading architecture diagrams",
        version="2.0.0",
        lifespan=lifespan,
    )

    Instrumentator().instrument(app).expose(app)

    # Rate limiting
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
        status_code=429, content={"detail": "Rate limit exceeded"}
    ))
    app.add_middleware(SlowAPIMiddleware)

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS: never combine "*" with credentials (browser would block it anyway,
    # but it also signals the operator that the configuration is wrong).
    raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8051")
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    if "*" in allowed_origins:
        # Refuse to use wildcard + credentials. Fall back to the safe default.
        allowed_origins = ["http://localhost:8051"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

    app.include_router(build_router(settings, limiter))

    return app
