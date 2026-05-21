"""Inbound/outbound ports (interfaces) — the application depends on these, not on adapters."""
from typing import Protocol, Optional, List

from app.domain.models import Upload


class StoragePort(Protocol):
    """Port for file storage operations."""
    async def upload_file(self, file_content: bytes, object_name: str, content_type: str) -> str:
        """Upload file and return storage URL."""
        ...


class UploadRepositoryPort(Protocol):
    """Port for upload persistence operations."""
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
        ...

    async def get_upload(self, upload_id: str) -> Optional[Upload]:
        """Retrieve an upload by ID."""
        ...

    async def list_uploads(self, limit: int = 50) -> List[Upload]:
        """List recent uploads."""
        ...

    async def update_status(self, upload_id: str, status: str) -> None:
        """Update upload status."""
        ...

    async def mark_processing(self, upload_id: str) -> None:
        """Set status PROCESSING — called when ai-service starts analysing."""
        ...

    async def mark_done_with_payload(self, upload_id: str, payload_json: str) -> None:
        """Set status DONE and persist the analysis JSON payload."""
        ...

    async def mark_failed(self, upload_id: str, error_message: str) -> None:
        """Set status ERROR and persist an error payload."""
        ...

    async def get_upload_stats(self) -> dict:
        """Return aggregate counts: {total: int, by_status: {status: count}}."""
        ...


class MessagePublisherPort(Protocol):
    """Port for publishing messages to queue."""
    async def publish_upload_event(
        self,
        upload_id: str,
        filename: str,
        file_path: str,
        content_type: str
    ) -> None:
        """Publish upload event to message queue."""
        ...
