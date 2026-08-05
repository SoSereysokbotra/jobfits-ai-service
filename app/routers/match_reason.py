"""Match-reasoning router (Phase C). Guarded by the service API key."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_current_settings, get_ollama_client, require_api_key
from app.schemas.match_reason import MatchReasonRequest, MatchReasonResponse
from app.services.match_reason_service import MatchReasonService
from app.services.ollama_client import OllamaClient

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/match/reason", response_model=MatchReasonResponse)
async def match_reason(
    request: MatchReasonRequest,
    ollama: OllamaClient = Depends(get_ollama_client),
    settings: Settings = Depends(get_current_settings),
) -> MatchReasonResponse:
    return await MatchReasonService(ollama, settings).reason(request)
