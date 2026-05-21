"""PostgreSQL (asyncpg) adapter for upload persistence."""
from datetime import datetime
from typing import Optional, List
from urllib.parse import urlparse
import logging

import asyncpg

from app.application.ports import UploadRepositoryPort
from app.domain.models import Upload

logger = logging.getLogger(__name__)


def parse_asyncpg_dsn(database_url: str) -> dict:
    """Turn postgresql+asyncpg://user:pass@host:port/db into asyncpg kwargs."""
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql+asyncpg", "postgresql"}:
        raise ValueError("Invalid DSN scheme. Expected postgresql+asyncpg:// or postgresql://")
    if not parsed.username or not parsed.password or not parsed.hostname or not parsed.path:
        raise ValueError("Invalid DSN. Must include username, password, host, and database name.")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path.lstrip("/"),
    }


class AsyncpgUploadRepository(UploadRepositoryPort):
    """PostgreSQL implementation of upload repository."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_upload(
        self,
        upload_id: str,
        filename: str,
        content_type: str,
        file_size: int,
        file_path: str,
        minio_url: str
    ) -> None:
        """Create a new upload record."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO uploads (id, filename, content_type, file_size, status, file_path, minio_url)
                VALUES ($1, $2, $3, $4, 'RECEIVED', $5, $6)
                """,
                upload_id,
                filename,
                content_type,
                file_size,
                file_path,
                minio_url,
            )

    async def get_upload(self, upload_id: str) -> Optional[Upload]:
        """Retrieve an upload by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM uploads WHERE id = $1",
                upload_id,
            )
            if not row:
                return None
            
            return Upload(
                id=str(row["id"]),
                filename=row["filename"],
                content_type=row["content_type"],
                file_size=row["file_size"],
                status=row["status"],
                file_path=row["file_path"],
                minio_url=row["minio_url"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def list_uploads(self, limit: int = 50) -> List[Upload]:
        """List recent uploads."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM uploads ORDER BY created_at DESC LIMIT $1",
                limit,
            )
            return [
                Upload(
                    id=str(r["id"]),
                    filename=r["filename"],
                    content_type=r["content_type"],
                    file_size=r["file_size"],
                    status=r["status"],
                    file_path=r["file_path"],
                    minio_url=r["minio_url"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    async def update_status(self, upload_id: str, status: str) -> None:
        """Update upload status."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE uploads SET status = $1, updated_at = NOW() WHERE id = $2",
                status,
                upload_id,
            )

    async def mark_processing(self, upload_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE uploads SET status = 'PROCESSING', updated_at = NOW() WHERE id = $1",
                upload_id,
            )

    async def mark_done_with_payload(self, upload_id: str, payload_json: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE uploads SET status = 'DONE', updated_at = NOW(), file_path = $1 WHERE id = $2",
                payload_json,
                upload_id,
            )

    async def mark_failed(self, upload_id: str, error_message: str) -> None:
        import json as _json
        payload = _json.dumps({"text": "", "ai": {"error": error_message}})
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE uploads SET status = 'ERROR', updated_at = NOW(), file_path = $1 WHERE id = $2",
                payload,
                upload_id,
            )

    async def get_upload_stats(self) -> dict:
        async with self._pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM uploads")
            rows = await conn.fetch(
                "SELECT status, COUNT(*) AS count FROM uploads GROUP BY status"
            )
            return {"total": int(total), "by_status": {r["status"]: int(r["count"]) for r in rows}}


class NullUploadRepository(UploadRepositoryPort):
    """No-op when the database is unavailable."""

    async def create_upload(
        self,
        upload_id: str,
        filename: str,
        content_type: str,
        file_size: int,
        file_path: str,
        minio_url: str
    ) -> None:
        return None

    async def get_upload(self, upload_id: str) -> Optional[Upload]:
        return None

    async def list_uploads(self, limit: int = 50) -> List[Upload]:
        return []

    async def update_status(self, upload_id: str, status: str) -> None:
        return None

    async def mark_processing(self, upload_id: str) -> None:
        return None

    async def mark_done_with_payload(self, upload_id: str, payload_json: str) -> None:
        return None

    async def mark_failed(self, upload_id: str, error_message: str) -> None:
        return None

    async def get_upload_stats(self) -> dict:
        return {"total": 0, "by_status": {}}


async def create_upload_repository(
    database_url: str,
) -> tuple[UploadRepositoryPort, Optional[asyncpg.Pool]]:
    """Factory function to create upload repository with connection pool."""
    if not database_url:
        return NullUploadRepository(), None
    try:
        kwargs = parse_asyncpg_dsn(database_url)
        pool = await asyncpg.create_pool(
            **kwargs,
            min_size=2,
            max_size=10,
        )
        
        # Create table if not exists
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
        
        return AsyncpgUploadRepository(pool), pool
    except Exception as e:
        logger.exception("Failed to initialize upload repository")
        return NullUploadRepository(), None
