"""PostgreSQL (asyncpg) adapter for report and feedback persistence."""
import json
from typing import Optional, List

import asyncpg

from app.application.ports import ReportRepositoryPort, FeedbackRepositoryPort
from app.domain.models import Report, ReportSummary, Statistics


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


class AsyncpgReportRepository(ReportRepositoryPort):
    """PostgreSQL implementation of report repository."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_report(self, upload_id: str) -> Optional[Report]:
        """Retrieve a report by upload ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM uploads WHERE id = $1",
                upload_id,
            )
            if not row:
                return None
            
            analysis = {}
            if row["file_path"]:
                try:
                    analysis = json.loads(row["file_path"])
                except:
                    analysis = {"raw": row["file_path"]}
            
            return Report(
                id=str(row["id"]),
                filename=row["filename"],
                status=row["status"],
                analysis=analysis,
                created_at=row["created_at"],
                minio_url=row.get("minio_url"),
                content_type=row.get("content_type"),
            )

    async def list_reports(self, status: Optional[str], limit: int) -> List[ReportSummary]:
        """List reports with optional status filter."""
        async with self._pool.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    """SELECT id, filename, status, created_at 
                       FROM uploads WHERE status = $1 
                       ORDER BY created_at DESC LIMIT $2""",
                    status.upper(),
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """SELECT id, filename, status, created_at 
                       FROM uploads ORDER BY created_at DESC LIMIT $1""",
                    limit,
                )
            
            return [
                ReportSummary(
                    id=str(r["id"]),
                    filename=r["filename"],
                    status=r["status"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    async def check_upload_exists(self, upload_id: str) -> bool:
        """Check if upload exists."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM uploads WHERE id = $1",
                upload_id,
            )
            return row is not None


class AsyncpgFeedbackRepository(FeedbackRepositoryPort):
    """PostgreSQL implementation of feedback repository."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_feedback(self, upload_id: str, rating: int, comment: Optional[str]) -> None:
        """Create feedback for an upload."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id SERIAL PRIMARY KEY,
                    upload_id UUID REFERENCES uploads(id),
                    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute(
                """INSERT INTO feedback (upload_id, rating, comment)
                   VALUES ($1, $2, $3)""",
                upload_id,
                rating,
                comment,
            )

    async def get_statistics(self) -> Statistics:
        """Get statistics about uploads and feedback."""
        async with self._pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM uploads")
            
            by_status = await conn.fetch(
                "SELECT status, COUNT(*) FROM uploads GROUP BY status"
            )
            by_status_dict = {r["status"]: r["count"] for r in by_status}
            
            avg_rating = await conn.fetchval(
                "SELECT AVG(rating)::NUMERIC(2,1) FROM feedback"
            )
            avg_rating = float(avg_rating) if avg_rating else 0.0
            
            total_feedback = await conn.fetchval("SELECT COUNT(*) FROM feedback") or 0
            
            return Statistics(
                total_uploads=total,
                by_status=by_status_dict,
                avg_rating=avg_rating,
                total_feedback=total_feedback,
            )


class NullReportRepository(ReportRepositoryPort):
    """No-op when the database is unavailable."""

    async def get_report(self, upload_id: str) -> Optional[Report]:
        return None

    async def list_reports(self, status: Optional[str], limit: int) -> List[ReportSummary]:
        return []

    async def check_upload_exists(self, upload_id: str) -> bool:
        return False


class NullFeedbackRepository(FeedbackRepositoryPort):
    """No-op when the database is unavailable."""

    async def create_feedback(self, upload_id: str, rating: int, comment: Optional[str]) -> None:
        return None

    async def get_statistics(self) -> Statistics:
        return Statistics(
            total_uploads=0,
            by_status={},
            avg_rating=0.0,
            total_feedback=0,
        )


async def create_repositories(
    database_url: str,
) -> tuple[ReportRepositoryPort, FeedbackRepositoryPort, Optional[asyncpg.Pool]]:
    """Factory function to create repositories with connection pool."""
    if not database_url:
        return NullReportRepository(), NullFeedbackRepository(), None
    try:
        kwargs = parse_asyncpg_dsn(database_url)
        pool = await asyncpg.create_pool(
            **kwargs,
            min_size=2,
            max_size=10,
        )
        
        return (
            AsyncpgReportRepository(pool),
            AsyncpgFeedbackRepository(pool),
            pool,
        )
    except Exception as e:
        print(f"DB Error: {e}")
        return NullReportRepository(), NullFeedbackRepository(), None
