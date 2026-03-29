"""Upload Service - FastAPI application."""
import os
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import aiobotocore.session
import asyncpg
import aio_pika
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://fiap:fiap@postgres:5432/fiap"
)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "fiap")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "fiap")

# MinIO/S3 Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "fiap")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "fiap1234")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "fiap")
MINIO_REGION = os.getenv("MINIO_REGION", "us-east-1")
MINIO_USE_SSL = os.getenv("MINIO_USE_SSL", "false").lower() == "true"

pool: asyncpg.Pool = None
rabbit_connection: aio_pika.RobustConnection = None
@asynccontextmanager
async def get_minio_client():
    """Get or create MinIO/S3 client."""
    session = aiobotocore.session.get_session()
    async with session.create_client(
        "s3",
        endpoint_url=f"{'https' if MINIO_USE_SSL else 'http'}://{MINIO_ENDPOINT}",
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name=MINIO_REGION,
    ) as client:
        yield client


async def ensure_bucket_exists(client):
    """Ensure the bucket exists, create if not."""
    try:
        await client.head_bucket(Bucket=MINIO_BUCKET)
    except:
        await client.create_bucket(Bucket=MINIO_BUCKET)


async def upload_to_minio(file_content: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
    """Upload file to MinIO and return the object URL."""
    async with get_minio_client() as client:
        await ensure_bucket_exists(client)
    
        await client.put_object(
            Bucket=MINIO_BUCKET,
            Key=object_name,
            Body=file_content,
            ContentType=content_type,
        )
    
    # Return MinIO URL
    return f"minio://{MINIO_BUCKET}/{object_name}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool, rabbit_connection
    
    # Parse DB URL
    db_url = DATABASE_URL.replace("postgresql+asyncpg://", "")
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
                minio_url TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            ALTER TABLE uploads ADD COLUMN IF NOT EXISTS minio_url TEXT
        """)
    
    # Connect to RabbitMQ
    rabbit_connection = await aio_pika.connect_robust(
        host=RABBITMQ_HOST, port=RABBITMQ_PORT,
        login=RABBITMQ_USER, password=RABBITMQ_PASSWORD
    )
    
    # Initialize MinIO client and ensure bucket exists
    try:
        async with get_minio_client() as minio:
            await ensure_bucket_exists(minio)
            print(f"MinIO bucket '{MINIO_BUCKET}' ready")
    except Exception as e:
        print(f"Warning: Could not connect to MinIO: {e}")
    
    yield
    
    await pool.close()
    await rabbit_connection.close()


app = FastAPI(
    title="Upload Service",
    description="API for uploading architecture diagrams",
    version="2.0.0",
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
    minio_url: Optional[str] = None


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "upload-service"}


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB")
    
    upload_id = str(uuid.uuid4())
    filename = file.filename
    content_type = file.content_type or "application/octet-stream"
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Upload to MinIO
    minio_url = None
    minio_object_name = f"uploads/{upload_id}_{filename}"
    try:
        minio_url = await upload_to_minio(content, minio_object_name, content_type)
        print(f"Uploaded to MinIO: {minio_url}")
    except Exception as e:
        print(f"Failed to upload to MinIO: {e}")
        # Continue anyway, save locally as fallback
        uploads_dir = "/app/uploads"
        os.makedirs(uploads_dir, exist_ok=True)
        local_path = f"{uploads_dir}/{upload_id}_{filename}"
        with open(local_path, "wb") as f:
            f.write(content)
        minio_url = f"local://{local_path}"
    
    # Save to DB
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO uploads (id, filename, content_type, file_size, status, file_path, minio_url)
               VALUES ($1, $2, $3, $4, 'RECEIVED', $5, $6)""",
            upload_id, filename, content_type, file_size, minio_url, minio_url
        )
    
    # Publish to RabbitMQ
    channel = await rabbit_connection.channel()
    await channel.default_exchange.publish(
        aio_pika.Message(body=json.dumps({
            "upload_id": upload_id,
            "filename": filename,
            "file_path": minio_url,
            "content_type": content_type
        }).encode()),
        routing_key="diagram.upload"
    )
    
    return UploadResponse(
        id=upload_id,
        filename=filename,
        status="RECEIVED",
        message="File uploaded successfully. Processing will start shortly.",
        minio_url=minio_url
    )


@app.get("/uploads")
async def list_uploads():
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, filename, status, created_at, minio_url FROM uploads ORDER BY created_at DESC LIMIT 50"
        )
        return [
            {
                "id": str(r["id"]),
                "filename": r["filename"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat(),
                "minio_url": r["minio_url"]
            }
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