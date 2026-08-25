"""Shared FastAPI dependencies (auth + client providers)."""

from __future__ import annotations

from fastapi import Header

from app.config import Settings, get_settings
from app.core.errors import AiServiceError, ErrorCode
from app.services.chat_router import ChatRouter
from app.services.ollama_client import OllamaClient


def require_api_key(x_ai_service_key: str | None = Header(default=None)) -> None:
    """Validate the `X-AI-Service-Key` header (service-to-service auth).

    Applied to every router except /health. Raises 401 on mismatch.
    """
    settings = get_settings()
    if x_ai_service_key != settings.ai_service_key:
        raise AiServiceError(
            ErrorCode.UNAUTHORIZED, "Invalid or missing X-AI-Service-Key", 401
        )


def get_ollama_client() -> OllamaClient:
    """Provide an OllamaClient built from current settings."""
    return OllamaClient(get_settings())


def get_chat_router() -> ChatRouter:
    """Provide a ChatRouter (task -> chat provider).

    Injected ONLY into the generate and job-requirements routers. Résumé, embed, rerank and
    match-reason keep depending on `get_ollama_client` directly, which is what makes the
    "personal data never leaves this machine" rule structural — see chat_router.py.
    """
    settings = get_settings()
    return ChatRouter(settings, OllamaClient(settings))


def get_current_settings() -> Settings:
    return get_settings()
