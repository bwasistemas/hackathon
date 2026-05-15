"""Composition root: wires adapters to use cases and builds the FastAPI application."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

from app.adapters.inbound.http_routes import build_router
from app.adapters.inbound.rabbitmq_consumer import (
    connect_rabbitmq,
    start_diagram_upload_consumer,
)
from app.adapters.outbound.asyncpg_uploads import create_upload_repository
from app.adapters.outbound.openai_adapter import OpenAiLlmAdapter, build_openai_client
from app.adapters.outbound.minio_storage import MinIOStorage
from app.adapters.outbound.llm_ocr import LlmOCRAdapter
from app.application.analyze_diagram import AnalyzeDiagramUseCase
from app.application.process_diagram_upload import ProcessDiagramUploadUseCase
from app.config import load_settings
from app.logging_config import setup_logging


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 50_000_000):  # 50 MB
        super().__init__(app)
        self.max_size = max_size
    
    async def dispatch(self, request: Request, call_next):
        if request.method not in ["POST", "PUT"]:
            return await call_next(request)
        
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"}
            )
        return await call_next(request)


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"}
    )


def create_app() -> FastAPI:
    settings = load_settings()
    
    # Setup logging
    setup_logging("ai-service")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        upload_repo, db_pool = await create_upload_repository(settings.database_url)
        app.state.db_pool = db_pool
        client = build_openai_client(settings.openai_api_key.get_secret_value(), settings.openai_base_url)
        llm = OpenAiLlmAdapter(client=client, model=settings.llm_model)
        ocr = LlmOCRAdapter(settings=settings)
        storage = MinIOStorage(settings)

        app.state.analyze_use_case = AnalyzeDiagramUseCase(llm)
        process_upload = ProcessDiagramUploadUseCase(ocr, llm, upload_repo, storage)

        rabbit = await connect_rabbitmq(
            settings.rabbitmq_host,
            settings.rabbitmq_port,
            settings.rabbitmq_user,
            settings.rabbitmq_password.get_secret_value(),
        )
        app.state.rabbit_connection = rabbit
        if rabbit:
            await start_diagram_upload_consumer(rabbit, process_upload)

        yield

        if db_pool:
            await db_pool.close()
        if rabbit:
            await rabbit.close()

    app = FastAPI(
        title="AI Service",
        description="AI-powered architecture analysis",
        version="1.0.0",
        lifespan=lifespan,
    )

    Instrumentator().instrument(app).expose(app)

    # Rate limiting
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Request size limit
    app.add_middleware(RequestSizeLimitMiddleware, max_size=50_000_000)

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS restricted to known frontend origins only.
    raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8051")
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    if "*" in allowed_origins:
        allowed_origins = ["http://localhost:8051"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["POST"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=600,
    )

    app.include_router(build_router(settings, limiter))

    return app
