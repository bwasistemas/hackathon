"""MinIO storage adapter for downloading files from object storage."""
import os
import tempfile
from contextlib import asynccontextmanager
from typing import Optional

import aiobotocore.session

from app.config import Settings


class MinIOStorage:
    """Adapter for downloading files from MinIO."""

    def __init__(self, settings: Settings) -> None:
        self._endpoint = settings.minio_endpoint
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key.get_secret_value()
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

    async def download_file(self, minio_url: str) -> str:
        """
        Download a file from MinIO and return local temp file path.
        
        Args:
            minio_url: URL in format 'minio://bucket/path/to/file'
        
        Returns:
            Local file path to downloaded file
        
        Raises:
            ValueError: If URL format is invalid
            Exception: If download fails
        """
        if not minio_url.startswith("minio://"):
            raise ValueError(f"Invalid MinIO URL format: {minio_url}")
        
        # Parse URL: minio://bucket/path/to/file
        url_without_scheme = minio_url.replace("minio://", "")
        parts = url_without_scheme.split("/", 1)
        
        if len(parts) != 2:
            raise ValueError(f"Invalid MinIO URL format: {minio_url}")
        
        bucket = parts[0]
        object_key = parts[1]
        
        # Download to temp file
        async with self._get_client() as client:
            response = await client.get_object(Bucket=bucket, Key=object_key)
            
            # Get file extension from object key
            _, ext = os.path.splitext(object_key)
            
            # Create temp file with same extension
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=ext
            )
            temp_path = temp_file.name
            
            # Read and write content
            async with response["Body"] as stream:
                content = await stream.read()
                temp_file.write(content)
                temp_file.close()
            
            return temp_path
