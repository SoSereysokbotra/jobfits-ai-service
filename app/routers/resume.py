"""Resume router (BUILD_PLAN.md §4.1 / §4.2). Guarded by the service API key."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_current_settings, get_ollama_client, require_api_key
from app.schemas.resume import (
    ParseRequest,
    ParseResponse,
    ScoreRequest,
    ScoreResponse,
)
from app.services.ollama_client import OllamaClient
from app.services.resume_service import ResumeService

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/resume/parse", response_model=ParseResponse)
async def parse(
    request: ParseRequest,
    ollama: OllamaClient = Depends(get_ollama_client),
    settings: Settings = Depends(get_current_settings),
) -> ParseResponse:
    return await ResumeService(ollama, settings).parse(request.text, request.file_type)


@router.post("/resume/score", response_model=ScoreResponse)
async def score(
    request: ScoreRequest,
    ollama: OllamaClient = Depends(get_ollama_client),
    settings: Settings = Depends(get_current_settings),
) -> ScoreResponse:
    return await ResumeService(ollama, settings).score(
        request.text, request.target_role
    )
