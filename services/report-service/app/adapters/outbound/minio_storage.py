"""MinIO storage adapter for downloading files from object storage."""
import os
import tempfile
from contextlib import asynccontextmanager

import aiobotocore.session

from app.config import Settings


class MinIOStorage:
    def __init__(self, settings: Settings) -> None:
        self._endpoint = settings.minio_endpoint
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key
        self._region = settings.minio_region
        self._use_ssl = settings.minio_use_ssl

    @asynccontextmanager
    async def _get_client(self):
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
        """Download file from minio://bucket/key and return local temp path."""
        if not minio_url.startswith("minio://"):
            raise ValueError(f"Invalid MinIO URL: {minio_url}")

        url_without_scheme = minio_url.replace("minio://", "")
        parts = url_without_scheme.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid MinIO URL: {minio_url}")

        bucket, object_key = parts[0], parts[1]
        _, ext = os.path.splitext(object_key)

        async with self._get_client() as client:
            response = await client.get_object(Bucket=bucket, Key=object_key)
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            async with response["Body"] as stream:
                content = await stream.read()
                temp_file.write(content)
                temp_file.close()
            return temp_file.name
