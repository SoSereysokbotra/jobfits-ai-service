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

    # DeepSeek — OPTIONAL hosted generation provider (docs/DEEPSEEK_PROVIDER_PLAN.md).
    # A blank key disables it entirely: every task then runs on Ollama exactly as before,
    # so a clone with no key behaves identically to a build without this feature.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    # `deepseek-chat`/`deepseek-reasoner` were retired 2026-07-24. Flash, not Pro: ~3x
    # cheaper, and none of the allowlisted tasks need a reasoning model.
    deepseek_model: str = "deepseek-v4-flash"
    # Comma-separated ALLOWLIST of task names that may leave this machine. Deny by
    # default: a task absent from this list runs on Ollama no matter what else is set.
    # NEVER add a résumé task — see chat_router.py for why that boundary is structural.
    deepseek_tasks: str = "interview,job_requirements"
    # Caps output length so a malformed prompt cannot burn prepaid credit.
    #
    # MEASURED, 2026-08-20 — why this is 4096 and not the 1024 it started as. Interview
    # question generation spent 963 completion tokens on an ordinary request, of which 205
    # were the model's own reasoning (V4-Flash bills reasoning inside the completion
    # budget). At 1024 the same call truncated mid-object and the JSON would not parse, so
    # the cap was silently corrupting output rather than guarding spend. 4096 clears the
    # observed ceiling ~4x; worst case is still well under a cent per call.
    deepseek_max_tokens: int = 4096

    # Service-to-service auth (must match backend AI_SERVICE_KEY)
    ai_service_key: str = "change-me"

    # Timeouts (seconds)
    request_timeout_generate: float = 60.0
    request_timeout_embed: float = 10.0
    request_timeout_deepseek: float = 30.0

    # Server
    port: int = 8000
    env: str = "development"


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the .env file is read only once per process."""
    return Settings()
