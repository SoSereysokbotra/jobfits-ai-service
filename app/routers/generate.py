"""Generation router (BUILD_PLAN.md §4.4 / §4.5). Guarded by the service API key."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_chat_router, get_current_settings, require_api_key
from app.schemas.generate import (
    CoverLetterRequest,
    CoverLetterResponse,
    InterviewRequest,
    InterviewResponse,
)
from app.services.chat_router import ChatRouter
from app.services.generate_service import GenerateService

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/generate/cover-letter", response_model=CoverLetterResponse)
async def cover_letter(
    request: CoverLetterRequest,
    chat: ChatRouter = Depends(get_chat_router),
    settings: Settings = Depends(get_current_settings),
) -> CoverLetterResponse:
    return await GenerateService(chat, settings).cover_letter(request)


@router.post("/generate/interview", response_model=InterviewResponse)
async def interview(
    request: InterviewRequest,
    chat: ChatRouter = Depends(get_chat_router),
    settings: Settings = Depends(get_current_settings),
) -> InterviewResponse:
    return await GenerateService(chat, settings).interview(request)
