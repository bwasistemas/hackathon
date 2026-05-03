"""Environment-backed settings (composition root reads these; domain stays pure)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""
    database_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_region: str
    minio_use_ssl: bool


def load_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://fiap:fiap@postgres:5432/fiap",
        ),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "fiap"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "fiap1234"),
        minio_region=os.getenv("MINIO_REGION", "us-east-1"),
        minio_use_ssl=os.getenv("MINIO_USE_SSL", "false").lower() == "true",
    )
