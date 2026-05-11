"""Environment-backed settings (composition root reads these; domain stays pure)."""
import logging
import os
from pydantic import BaseModel, SecretStr

logger = logging.getLogger(__name__)

_INSECURE_JWT_VALUES = frozenset(
    {
        "your-secret-key-here-change-in-production",
        "replace-with-a-64-char-random-string",
    }
)


def _require_jwt_secret() -> str:
    """The ai-service does not issue tokens, but it MUST share the same secret
    as the upload-service in order to validate them."""
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not secret or secret in _INSECURE_JWT_VALUES:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set or still uses the insecure default. "
            "It must match the value configured on the upload-service."
        )
    if len(secret) < 32:
        logger.warning("JWT_SECRET_KEY is shorter than 32 chars; consider rotating to a longer value")
    return secret


class Settings(BaseModel):
    openai_api_key: SecretStr
    openai_base_url: str
    llm_model: str
    llm_ocr: str
    database_url: str
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_user: str
    rabbitmq_password: SecretStr
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: SecretStr
    minio_bucket: str
    minio_region: str
    minio_use_ssl: bool
    max_handoffs: int
    max_iterations: int
    execution_timeout: float
    node_timeout: float
    repetitive_handoff_detection_window: int
    repetitive_handoff_min_unique_agents: int
    jwt_secret_key: SecretStr
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int

    def __repr__(self):
        # Safe representation for logging
        return (
            "Settings(openai_api_key=*****, rabbitmq_password=*****, "
            "minio_secret_key=*****, jwt_secret_key=*****, ...)"
        )


def load_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        llm_model=os.getenv("LLM_MODEL", "deepseek/deepseek-v3.2"),
        llm_ocr=os.getenv("LLM_OCR", "google/gemma-4-26b-a4b-it"),
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
        max_handoffs=int(os.getenv("MAX_HANDOFFS", "20")),
        max_iterations=int(os.getenv("MAX_ITERATIONS", "20")),
        execution_timeout=float(os.getenv("EXECUTION_TIMEOUT", "60.0")),
        node_timeout=float(os.getenv("NODE_TIMEOUT", "30.0")),
        repetitive_handoff_detection_window=int(os.getenv("REPETITIVE_HANDOFF_DETECTION_WINDOW", "8")),
        repetitive_handoff_min_unique_agents=int(os.getenv("REPETITIVE_HANDOFF_MIN_UNIQUE_AGENTS", "3")),
        jwt_secret_key=_require_jwt_secret(),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_access_token_expire_minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")),
    )
