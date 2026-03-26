"""PostgreSQL (asyncpg) adapter for upload status and AI payload."""
from typing import Optional

import asyncpg

from app.application.ports import UploadRepositoryPort


def parse_asyncpg_dsn(database_url: str) -> dict:
    """Turn postgresql+asyncpg://user:pass@host:port/db into asyncpg kwargs."""
    db_url = database_url.replace("postgresql+asyncpg://", "")
    user_part, rest = db_url.split("@", 1)
    user = user_part.split(":")[0]
    password = ":".join(user_part.split(":")[1:])
    host_port_db = rest
    host_port, db = host_port_db.rsplit("/", 1)
    host, port = host_port.rsplit(":", 1)
    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "database": db,
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


class NullUploadRepository(UploadRepositoryPort):
    """No-op when the database is unavailable."""

    async def mark_processing(self, upload_id: str) -> None:
        return None

    async def mark_done_with_payload(self, upload_id: str, payload_json: str) -> None:
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
        print(f"DB Error: {e}")
        return NullUploadRepository(), None
