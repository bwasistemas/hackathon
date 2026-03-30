"""Composition root: wires adapters to use cases and builds the FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.adapters.inbound.http_routes import build_router
from app.adapters.inbound.rabbitmq_consumer import (
    connect_rabbitmq,
    start_diagram_upload_consumer,
)
from app.adapters.outbound.asyncpg_uploads import create_upload_repository
from app.adapters.outbound.strands_multi_agents_adapter import SwarmLlmAdapter, build_multi_agents
from app.adapters.outbound.tesseract_ocr import TesseractTextExtractor
from app.application.analyze_diagram import AnalyzeDiagramUseCase
from app.application.process_diagram_upload import ProcessDiagramUploadUseCase
from app.config import load_settings

def create_app() -> FastAPI:
    settings = load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        upload_repo, db_pool = await create_upload_repository(settings.database_url)
        app.state.db_pool = db_pool
        multi_agents = build_multi_agents()
        llm = SwarmLlmAdapter(multi_agents)
        ocr = TesseractTextExtractor()

        app.state.analyze_use_case = AnalyzeDiagramUseCase(llm)
        process_upload = ProcessDiagramUploadUseCase(ocr, llm, upload_repo)

        rabbit = await connect_rabbitmq(
            settings.rabbitmq_host,
            settings.rabbitmq_port,
            settings.rabbitmq_user,
            settings.rabbitmq_password,
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_router())

    return app
