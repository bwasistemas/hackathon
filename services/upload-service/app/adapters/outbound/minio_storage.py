"""MinIO storage adapter for uploading files to object storage."""
from contextlib import asynccontextmanager

import aiobotocore.session

from app.application.ports import StoragePort
from app.config import Settings


class MinIOStorageAdapter(StoragePort):
    """Adapter for uploading files to MinIO."""

    def __init__(self, settings: Settings) -> None:
        self._endpoint = settings.minio_endpoint
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key
        self._bucket = settings.minio_bucket
        self._region = settings.minio_region
        self._use_ssl = settings.minio_use_ssl

    @asynccontextmanager
    async def _get_client(self):
        """Get MinIO/S3 client."""
        session = aiobotocore.session.get_session()
        async with session.create_client(
            "s3",
            endpoint_url=f"{'https' if self._use_ssl else 'http'}://{self._endpoint}",
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        ) as client:
            yield client

    async def _ensure_bucket_exists(self, client) -> None:
        """Ensure the bucket exists, create if not."""
        try:
            await client.head_bucket(Bucket=self._bucket)
        except:
            await client.create_bucket(Bucket=self._bucket)

    async def upload_file(
        self,
        file_content: bytes,
        object_name: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload file to MinIO and return the object URL.
        
        Args:
            file_content: File content bytes
            object_name: Object name/path in bucket
            content_type: MIME type of the file
        
        Returns:
            MinIO URL in format 'minio://bucket/object_name'
        """
        async with self._get_client() as client:
            await self._ensure_bucket_exists(client)
        
            await client.put_object(
                Bucket=self._bucket,
                Key=object_name,
                Body=file_content,
                ContentType=content_type,
            )
        
        return f"minio://{self._bucket}/{object_name}"
