"""Job requirement extraction router. Guarded by the service API key."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_current_settings, get_ollama_client, require_api_key
from app.schemas.job_requirements import (
    JobRequirementsRequest,
    JobRequirementsResponse,
)
from app.services.job_requirements_service import JobRequirementsService
from app.services.ollama_client import OllamaClient

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/job/requirements", response_model=JobRequirementsResponse)
async def extract_requirements(
    request: JobRequirementsRequest,
    ollama: OllamaClient = Depends(get_ollama_client),
    settings: Settings = Depends(get_current_settings),
) -> JobRequirementsResponse:
    return await JobRequirementsService(ollama, settings).extract(request)
