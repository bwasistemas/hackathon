"""HTTP client adapter: implements ReportRepositoryPort via upload-service REST API."""
import logging
import time
from typing import Optional, List

import httpx

from app.application.ports import ReportRepositoryPort
from app.domain.models import Report, ReportSummary

logger = logging.getLogger(__name__)

_TOKEN_REFRESH_MARGIN_SECONDS = 60


class HttpUploadClientAdapter(ReportRepositoryPort):
    """Calls upload-service HTTP API to satisfy ReportRepositoryPort."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/token",
                data={"username": self._username, "password": self._password},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            # Assume 30-minute expiry; refresh 60s before it expires
            self._token_expires_at = time.monotonic() + 30 * 60 - _TOKEN_REFRESH_MARGIN_SECONDS
            logger.debug("Obtained service token from upload-service")
        return self._token

    async def _headers(self) -> dict:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}"}

    async def get_report(self, upload_id: str) -> Optional[Report]:
        import json as _json
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/uploads/{upload_id}",
                headers=headers,
                timeout=10,
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

        analysis: dict = {}
        raw_file_path = data.get("file_path") or ""
        if raw_file_path:
            try:
                analysis = _json.loads(raw_file_path)
            except (_json.JSONDecodeError, TypeError):
                analysis = {"raw": raw_file_path}

        from datetime import datetime
        return Report(
            id=data["id"],
            filename=data["filename"],
            status=data["status"],
            analysis=analysis,
            created_at=datetime.fromisoformat(data["created_at"]),
            minio_url=data.get("minio_url"),
            content_type=data.get("content_type"),
        )

    async def list_reports(self, status: Optional[str], limit: int) -> List[ReportSummary]:
        from datetime import datetime
        headers = await self._headers()
        params: dict = {"limit": limit}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/uploads",
                headers=headers,
                params=params,
                timeout=10,
            )
        resp.raise_for_status()
        items = resp.json()
        summaries = [
            ReportSummary(
                id=item["id"],
                filename=item["filename"],
                status=item["status"],
                created_at=datetime.fromisoformat(item["created_at"]),
            )
            for item in items
        ]
        if status:
            summaries = [s for s in summaries if s.status.upper() == status.upper()]
        return summaries[:limit]

    async def check_upload_exists(self, upload_id: str) -> bool:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/uploads/{upload_id}",
                headers=headers,
                timeout=10,
            )
        return resp.status_code == 200

    async def get_upload_counts(self) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/stats/uploads",
                headers=headers,
                timeout=10,
            )
        resp.raise_for_status()
        return resp.json()


class NullReportRepository(ReportRepositoryPort):
    """No-op when upload-service is unreachable."""

    async def get_report(self, upload_id: str) -> Optional[Report]:
        return None

    async def list_reports(self, status: Optional[str], limit: int) -> List[ReportSummary]:
        return []

    async def check_upload_exists(self, upload_id: str) -> bool:
        return False

    async def get_upload_counts(self) -> dict:
        return {"total": 0, "by_status": {}}
