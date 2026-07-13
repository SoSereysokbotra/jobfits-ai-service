"""Embedding router (BUILD_PLAN.md §4.3). Guarded by the service API key."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_current_settings, get_ollama_client, require_api_key
from app.schemas.embed import EmbedRequest, EmbedResponse
from app.services.embed_service import EmbedService
from app.services.ollama_client import OllamaClient

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/embed", response_model=EmbedResponse)
async def embed(
    request: EmbedRequest,
    ollama: OllamaClient = Depends(get_ollama_client),
    settings: Settings = Depends(get_current_settings),
) -> EmbedResponse:
    return await EmbedService(ollama, settings).embed(request.inputs)
