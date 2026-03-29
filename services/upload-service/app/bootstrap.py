"""Composition root: wires adapters to use cases and builds the FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.adapters.inbound.http_routes import build_router
from app.adapters.outbound.asyncpg_uploads import create_upload_repository
from app.adapters.outbound.minio_storage import MinIOStorageAdapter
from app.adapters.outbound.rabbitmq_publisher import RabbitMQPublisher, NullMessagePublisher, connect_rabbitmq
from app.application.upload_file import UploadFileUseCase, ListUploadsUseCase, GetUploadUseCase
from app.config import load_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = load_settings()

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
        
        if rabbit_connection:
            publisher = RabbitMQPublisher(rabbit_connection)
        else:
            publisher = NullMessagePublisher()

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_router())

    return app
