"""Environment-backed settings (composition root reads these; domain stays pure)."""
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_INSECURE_JWT_DEFAULT = "your-secret-key-here-change-in-production"


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""
    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_region: str
    minio_use_ssl: bool

def _require_jwt_secret() -> str:
    """The report-service does not issue tokens, but it MUST share the same
    secret as the upload-service in order to validate them."""
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not secret or secret == _INSECURE_JWT_DEFAULT:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set or still uses the insecure default. "
            "It must match the value configured on the upload-service."
        )
    if len(secret) < 32:
        logger.warning("JWT_SECRET_KEY is shorter than 32 chars; consider rotating to a longer value")
    return secret


def load_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://fiap:fiap@postgres:5432/fiap",
        ),
        jwt_secret_key=_require_jwt_secret(),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_access_token_expire_minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "fiap"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "fiap1234"),
        minio_region=os.getenv("MINIO_REGION", "us-east-1"),
        minio_use_ssl=os.getenv("MINIO_USE_SSL", "false").lower() == "true",
    )
