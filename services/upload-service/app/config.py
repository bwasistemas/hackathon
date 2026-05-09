"""Environment-backed settings (composition root reads these; domain stays pure)."""
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Sentinel value used by the .env.example file. If this leaks into runtime it
# means the operator never rotated the secret – we refuse to start.
_INSECURE_JWT_DEFAULT = "your-secret-key-here-change-in-production"


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""
    database_url: str
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_region: str
    minio_use_ssl: bool
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    admin_user: str
    admin_password: str


def _require_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not secret or secret == _INSECURE_JWT_DEFAULT:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set or still uses the insecure default. "
            "Generate a strong key (e.g. `python -c \"import secrets; "
            "print(secrets.token_urlsafe(48))\"`) and export it before starting "
            "the service."
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
        rabbitmq_host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
        rabbitmq_port=int(os.getenv("RABBITMQ_PORT", "5672")),
        rabbitmq_user=os.getenv("RABBITMQ_USER", "fiap"),
        rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", "fiap"),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "fiap"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "fiap1234"),
        minio_bucket=os.getenv("MINIO_BUCKET", "fiap"),
        minio_region=os.getenv("MINIO_REGION", "us-east-1"),
        minio_use_ssl=os.getenv("MINIO_USE_SSL", "false").lower() == "true",
        jwt_secret_key=_require_jwt_secret(),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_access_token_expire_minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")),
        admin_user=os.getenv("ADMIN_USER", ""),
        admin_password=os.getenv("ADMIN_PASSWORD", ""),
    )
