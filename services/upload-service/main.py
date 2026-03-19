"""Upload Service - FastAPI application."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncpg
import aio_pika
import json
import uuid
from datetime import datetime


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://archanalyzer:changeme@postgres:5432/archanalyzer"
)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "archanalyzer")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "changeme_secure_password")

pool: asyncpg.Pool = None
rabbit_connection: aio_pika.RobustConnection = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool, rabbit_connection
    
    # Parse DB URL
    db_url = DATABASE_URL.replace("postgresql+asyncpg://", "")
    # Format: user:password@host:port/db
    user_part, rest = db_url.split("@", 1)
    user = user_part.split(":")[0]
    password = ":".join(user_part.split(":")[1:])
    host_port_db = rest
    host_port, db = host_port_db.rsplit("/", 1)
    host, port = host_port.rsplit(":", 1)
    
    # Connect to PostgreSQL
    pool = await asyncpg.create_pool(
        host=host, port=int(port),
        user=user, password=password,
        database=db, min_size=2, max_size=10
    )
    
    # Create tables
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id UUID PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                content_type VARCHAR(100),
                file_size INTEGER,
                status VARCHAR(50) DEFAULT 'RECEIVED',
                file_path TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
    
    # Connect to RabbitMQ
    rabbit_connection = await aio_pika.connect_robust(
        host=RABBITMQ_HOST, port=RABBITMQ_PORT,
        login=RABBITMQ_USER, password=RABBITMQ_PASSWORD
    )
    
    yield
    
    await pool.close()
    await rabbit_connection.close()


from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(
    title="Upload Service",
    description="API for uploading architecture diagrams",
    version="1.0.0",
    lifespan=lifespan
)

Instrumentator().instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UploadResponse(BaseModel):
    id: str
    filename: str
    status: str
    message: str


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "upload-service"}


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB")
    
    upload_id = str(uuid.uuid4())
    filename = file.filename
    
    # Save to DB
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO uploads (id, filename, content_type, file_size, status)
               VALUES ($1, $2, $3, $4, 'RECEIVED')""",
            upload_id, filename, file.content_type, file.size
        )
    
    # Save file
    uploads_dir = "/app/uploads"
    os.makedirs(uploads_dir, exist_ok=True)
    
    file_path = f"{uploads_dir}/{upload_id}_{filename}"
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Publish to RabbitMQ
    channel = await rabbit_connection.channel()
    await channel.default_exchange.publish(
        aio_pika.Message(body=json.dumps({
            "upload_id": upload_id,
            "filename": filename,
            "file_path": file_path
        }).encode()),
        routing_key="diagram.upload"
    )
    
    return UploadResponse(
        id=upload_id,
        filename=filename,
        status="RECEIVED",
        message="File uploaded successfully. Processing will start shortly."
    )


@app.get("/uploads")
async def list_uploads():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, filename, status, created_at FROM uploads ORDER BY created_at DESC LIMIT 50"
        )
        return [
            {"id": str(r["id"]), "filename": r["filename"], 
             "status": r["status"], "created_at": r["created_at"].isoformat()}
            for r in rows
        ]


@app.get("/uploads/{upload_id}")
async def get_upload(upload_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM uploads WHERE id = $1", upload_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Upload not found")
        return dict(row)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)