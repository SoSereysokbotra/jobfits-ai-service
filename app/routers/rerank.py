"""Rerank router (Phase B). Guarded by the service API key."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_current_settings, get_ollama_client, require_api_key
from app.schemas.rerank import RerankRequest, RerankResponse
from app.services.ollama_client import OllamaClient
from app.services.rerank_service import RerankService

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/rerank", response_model=RerankResponse)
async def rerank(
    request: RerankRequest,
    ollama: OllamaClient = Depends(get_ollama_client),
    settings: Settings = Depends(get_current_settings),
) -> RerankResponse:
    return await RerankService(ollama, settings).rerank(request)
