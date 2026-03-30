"""Environment-backed settings (composition root reads these; domain stays pure)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""
    database_url: str


def load_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://fiap:fiap@postgres:5432/fiap",
        ),
    )
