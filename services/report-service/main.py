"""Report Service - API for retrieving analysis reports and feedback."""
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncpg
import json


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://archanalyzer:changeme@postgres:5432/archanalyzer"
)

from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(
    title="Report Service",
    description="API for retrieving analysis reports and feedback",
    version="1.0.0"
)

Instrumentator().instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pool: asyncpg.Pool = None


@app.on_event("startup")
async def startup():
    global pool
    db_url = DATABASE_URL.replace("postgresql+asyncpg://", "")
    user_part, rest = db_url.split("@", 1)
    user = user_part.split(":")[0]
    password = ":".join(user_part.split(":")[1:])
    host_port_db = rest
    host_port, db = host_port_db.rsplit("/", 1)
    host, port = host_port.rsplit(":", 1)
    
    pool = await asyncpg.create_pool(
        host=host, port=int(port),
        user=user, password=password,
        database=db, min_size=2, max_size=10
    )


@app.on_event("shutdown")
async def shutdown():
    await pool.close()


class FeedbackRequest(BaseModel):
    upload_id: str
    rating: int
    comment: Optional[str] = None


class ReportResponse(BaseModel):
    id: str
    filename: str
    status: str
    analysis: dict
    created_at: str


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "report-service"}

@app.get("/health/db")
async def health_db():
    try:
        if pool:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return {"status": "online"}
    except Exception:
        pass
    raise HTTPException(status_code=503, detail="Database Offline")


@app.get("/reports/{upload_id}", response_model=ReportResponse)
async def get_report(upload_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM uploads WHERE id = $1", upload_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
        
        analysis = {}
        if row["file_path"]:
            try:
                analysis = json.loads(row["file_path"])
            except:
                analysis = {"raw": row["file_path"]}
        
        return ReportResponse(
            id=str(row["id"]),
            filename=row["filename"],
            status=row["status"],
            analysis=analysis,
            created_at=row["created_at"].isoformat()
        )


@app.get("/reports")
async def list_reports(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100)
):
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                """SELECT id, filename, status, created_at 
                   FROM uploads WHERE status = $1 
                   ORDER BY created_at DESC LIMIT $2""",
                status.upper(), limit
            )
        else:
            rows = await conn.fetch(
                """SELECT id, filename, status, created_at 
                   FROM uploads ORDER BY created_at DESC LIMIT $1""",
                limit
            )
        
        return [
            {
                "id": str(r["id"]),
                "filename": r["filename"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat()
            }
            for r in rows
        ]


@app.post("/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    if not 1 <= feedback.rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    
    async with pool.acquire() as conn:
        # Check if upload exists
        row = await conn.fetchrow(
            "SELECT id FROM uploads WHERE id = $1", feedback.upload_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Upload not found")
        
        # Create feedback table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id SERIAL PRIMARY KEY,
                upload_id UUID REFERENCES uploads(id),
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Insert feedback
        await conn.execute(
            """INSERT INTO feedback (upload_id, rating, comment)
               VALUES ($1, $2, $3)""",
            feedback.upload_id, feedback.rating, feedback.comment
        )
    
    return {"message": "Feedback submitted successfully", "rating": feedback.rating}


@app.get("/stats")
async def get_stats():
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM uploads")
        by_status = await conn.fetch(
            "SELECT status, COUNT(*) FROM uploads GROUP BY status"
        )
        by_status_dict = {r["status"]: r["count"] for r in by_status}
        
        # Feedback stats
        avg_rating = await conn.fetchval(
            "SELECT AVG(rating)::NUMERIC(2,1) FROM feedback"
        ) or 0
        
        total_feedback = await conn.fetchval("SELECT COUNT(*) FROM feedback")
        
        return {
            "total_uploads": total,
            "by_status": by_status_dict,
            "avg_rating": float(avg_rating),
            "total_feedback": total_feedback
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)