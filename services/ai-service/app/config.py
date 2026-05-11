"""Environment-backed settings (composition root reads these; domain stays pure)."""
import os
from pydantic import BaseModel, SecretStr


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

    def __repr__(self):
        # Safe representation for logging
        return f"Settings(openai_api_key=*****, rabbitmq_password=*****, minio_secret_key=*****, ...)"


def load_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        llm_model=os.getenv("LLM_MODEL", "deepseek/deepseek-v3.2"),
        llm_ocr=os.getenv("LLM_OCR", "google/gemma-4-26b-a4b-it:free"),
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
    )
