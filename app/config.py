"""Settings loaded from environment (.env) via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Env var names are matched case-insensitively, so
    `OLLAMA_URL` in .env maps to `ollama_url` here (see .env.example)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Ollama
    ollama_url: str = "http://localhost:11434"
    generation_model: str = "qwen3"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    # Service-to-service auth (must match backend AI_SERVICE_KEY)
    ai_service_key: str = "change-me"

    # Timeouts (seconds)
    request_timeout_generate: float = 60.0
    request_timeout_embed: float = 10.0

    # Server
    port: int = 8000
    env: str = "development"


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the .env file is read only once per process."""
    return Settings()
