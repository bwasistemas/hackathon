"""PostgreSQL (asyncpg) adapter — report-service owns only the feedback table."""
import logging
from typing import Optional

import asyncpg

from app.application.ports import FeedbackRepositoryPort

logger = logging.getLogger(__name__)


def parse_asyncpg_dsn(database_url: str) -> dict:
    """Turn postgresql+asyncpg://user:pass@host:port/db into asyncpg kwargs."""
    db_url = database_url.replace("postgresql+asyncpg://", "")
    # rfind para lidar com senhas que contenham '@'
    last_at = db_url.rfind("@")
    user_part = db_url[:last_at]
    rest = db_url[last_at + 1:]
    user = user_part.split(":")[0]
    password = ":".join(user_part.split(":")[1:])
    host_port, db = rest.rsplit("/", 1)
    host, port = host_port.rsplit(":", 1)
    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "database": db,
    }


class AsyncpgFeedbackRepository(FeedbackRepositoryPort):
    """PostgreSQL implementation of feedback repository (arch_reports database)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_feedback(self, upload_id: str, rating: int, comment: Optional[str]) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO feedback (upload_id, rating, comment)
                   VALUES ($1, $2, $3)""",
                upload_id,
                rating,
                comment,
            )

    async def get_feedback_stats(self) -> dict:
        async with self._pool.acquire() as conn:
            avg_rating = await conn.fetchval(
                "SELECT AVG(rating)::NUMERIC(2,1) FROM feedback"
            )
            total_feedback = await conn.fetchval("SELECT COUNT(*) FROM feedback") or 0
            return {
                "avg_rating": float(avg_rating) if avg_rating else 0.0,
                "total_feedback": int(total_feedback),
            }


class NullFeedbackRepository(FeedbackRepositoryPort):
    """No-op when the database is unavailable."""

    async def create_feedback(self, upload_id: str, rating: int, comment: Optional[str]) -> None:
        return None

    async def get_feedback_stats(self) -> dict:
        return {"avg_rating": 0.0, "total_feedback": 0}


async def create_feedback_repository(
    database_url: str,
) -> tuple[FeedbackRepositoryPort, Optional[asyncpg.Pool]]:
    """Factory: creates feedback repository and runs schema migration."""
    if not database_url:
        return NullFeedbackRepository(), None
    try:
        kwargs = parse_asyncpg_dsn(database_url)
        pool = await asyncpg.create_pool(**kwargs, min_size=2, max_size=10)

        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id SERIAL PRIMARY KEY,
                    upload_id UUID NOT NULL,
                    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

        return AsyncpgFeedbackRepository(pool), pool
    except Exception:
        logger.exception("Failed to initialize feedback repository")
        return NullFeedbackRepository(), None
