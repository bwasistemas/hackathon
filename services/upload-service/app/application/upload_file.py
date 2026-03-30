"""Use case: upload file to storage and publish event."""
import uuid
from typing import Optional

from app.application.ports import StoragePort, UploadRepositoryPort, MessagePublisherPort
from app.domain.exceptions import FileTooLargeError, StorageError, MessageQueueError
from app.domain.models import UploadResult, Upload


class UploadFileUseCase:
    """Use case: upload file, persist metadata, and publish event."""
    
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    def __init__(
        self,
        storage: StoragePort,
        repository: UploadRepositoryPort,
        publisher: MessagePublisherPort,
    ) -> None:
        self._storage = storage
        self._repository = repository
        self._publisher = publisher
    
    async def execute(
        self,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> UploadResult:
        """Execute the upload file use case."""
        if len(content) > self.MAX_FILE_SIZE:
            raise FileTooLargeError(f"File too large. Max {self.MAX_FILE_SIZE / (1024*1024)}MB")
        
        upload_id = str(uuid.uuid4())
        
        # Upload to storage
        try:
            object_name = f"uploads/{upload_id}_{filename}"
            minio_url = await self._storage.upload_file(content, object_name, content_type)
        except Exception as e:
            raise StorageError(f"Failed to upload file to storage: {e}") from e
        
        # Save to repository
        try:
            await self._repository.create_upload(
                upload_id=upload_id,
                filename=filename,
                content_type=content_type,
                file_size=len(content),
                file_path=minio_url,
                minio_url=minio_url,
            )
        except Exception as e:
            raise StorageError(f"Failed to save upload metadata: {e}") from e
        
        # Publish event
        try:
            await self._publisher.publish_upload_event(
                upload_id=upload_id,
                filename=filename,
                file_path=minio_url,
                content_type=content_type,
            )
        except Exception as e:
            raise MessageQueueError(f"Failed to publish upload event: {e}") from e
        
        return UploadResult(
            id=upload_id,
            filename=filename,
            status="RECEIVED",
            message="File uploaded successfully. Processing will start shortly.",
            minio_url=minio_url,
        )


class ListUploadsUseCase:
    """Use case: list recent uploads."""
    
    def __init__(self, repository: UploadRepositoryPort) -> None:
        self._repository = repository
    
    async def execute(self, limit: int = 50) -> list[UploadResult]:
        """List recent uploads."""
        uploads = await self._repository.list_uploads(limit)
        return [
            UploadResult(
                id=u.id,
                filename=u.filename,
                status=u.status,
                message="",
                minio_url=u.minio_url,
            )
            for u in uploads
        ]


class GetUploadUseCase:
    """Use case: get upload details by ID."""
    
    def __init__(self, repository: UploadRepositoryPort) -> None:
        self._repository = repository
    
    async def execute(self, upload_id: str) -> Optional[Upload]:
        """Get upload by ID."""
        return await self._repository.get_upload(upload_id)
