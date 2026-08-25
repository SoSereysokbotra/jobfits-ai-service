"""Job requirement extraction router. Guarded by the service API key."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_chat_router, get_current_settings, require_api_key
from app.schemas.job_requirements import (
    JobRequirementsRequest,
    JobRequirementsResponse,
)
from app.services.chat_router import ChatRouter
from app.services.job_requirements_service import JobRequirementsService

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/job/requirements", response_model=JobRequirementsResponse)
async def extract_requirements(
    request: JobRequirementsRequest,
    chat: ChatRouter = Depends(get_chat_router),
    settings: Settings = Depends(get_current_settings),
) -> JobRequirementsResponse:
    return await JobRequirementsService(chat, settings).extract(request)
