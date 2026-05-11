"""PostgreSQL (asyncpg) adapter for upload status and AI payload."""
import json
import logging
from typing import Optional
from urllib.parse import urlparse

import asyncpg

from app.application.ports import UploadRepositoryPort

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
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def mark_processing(self, upload_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE uploads SET status = 'PROCESSING', updated_at = NOW() WHERE id = $1",
                upload_id,
            )

    async def mark_done_with_payload(self, upload_id: str, payload_json: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                    UPDATE uploads SET
                        status = 'DONE',
                        updated_at = NOW(),
                        file_path = $1
                    WHERE id = $2
                """,
                payload_json,
                upload_id,
            )

    async def mark_failed(self, upload_id: str, error_message: str) -> None:
        payload = json.dumps({"text": "", "ai": {"error": error_message}})
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                    UPDATE uploads SET
                        status = 'ERROR',
                        updated_at = NOW(),
                        file_path = $1
                    WHERE id = $2
                """,
                payload,
                upload_id,
            )


class NullUploadRepository(UploadRepositoryPort):
    """No-op when the database is unavailable."""

    async def mark_processing(self, upload_id: str) -> None:
        return None

    async def mark_done_with_payload(self, upload_id: str, payload_json: str) -> None:
        return None

    async def mark_failed(self, upload_id: str, error_message: str) -> None:
        return None


async def create_upload_repository(
    database_url: str,
) -> tuple[UploadRepositoryPort, Optional[asyncpg.Pool]]:
    if not database_url:
        return NullUploadRepository(), None
    try:
        kwargs = parse_asyncpg_dsn(database_url)
        pool = await asyncpg.create_pool(
            **kwargs,
            min_size=2,
            max_size=10,
        )
        return AsyncpgUploadRepository(pool), pool
    except Exception as e:
        logger.exception("Failed to initialize upload status repository")
        return NullUploadRepository(), None
