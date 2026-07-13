"""Generation router (BUILD_PLAN.md §4.4 / §4.5). Guarded by the service API key."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_current_settings, get_ollama_client, require_api_key
from app.schemas.generate import (
    CoverLetterRequest,
    CoverLetterResponse,
    InterviewRequest,
    InterviewResponse,
)
from app.services.generate_service import GenerateService
from app.services.ollama_client import OllamaClient

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/generate/cover-letter", response_model=CoverLetterResponse)
async def cover_letter(
    request: CoverLetterRequest,
    ollama: OllamaClient = Depends(get_ollama_client),
    settings: Settings = Depends(get_current_settings),
) -> CoverLetterResponse:
    return await GenerateService(ollama, settings).cover_letter(request)


@router.post("/generate/interview", response_model=InterviewResponse)
async def interview(
    request: InterviewRequest,
    ollama: OllamaClient = Depends(get_ollama_client),
    settings: Settings = Depends(get_current_settings),
) -> InterviewResponse:
    return await GenerateService(ollama, settings).interview(request)
