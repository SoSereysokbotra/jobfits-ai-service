"""Generation logic — cover letter + interview (BUILD_PLAN.md §6 Phase 4).

Cover letters and interview feedback are free text (json_mode=False). Interview
question generation is structured, so it runs in JSON mode and is validated
against InterviewResponse.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.config import Settings
from app.core.errors import AiServiceError, ErrorCode
from app.core.json_repair import extract_json
from app.core.prompts import load_prompt
from app.schemas.generate import (
    CoverLetterRequest,
    CoverLetterResponse,
    InterviewRequest,
    InterviewResponse,
)
from app.services.ollama_client import OllamaClient


class GenerateService:
    def __init__(self, ollama: OllamaClient, settings: Settings) -> None:
        self._ollama = ollama
        self._settings = settings

    async def cover_letter(self, req: CoverLetterRequest) -> CoverLetterResponse:
        payload = json.dumps(
            {
                "resumeSummary": req.resume_summary,
                "jobTitle": req.job_title,
                "companyName": req.company_name,
                "jobDescription": req.job_description,
                "tone": req.tone,
            }
        )
        text = await self._chat_text("cover_letter.txt", payload, "cover letter")
        return CoverLetterResponse(cover_letter=text)

    async def interview(self, req: InterviewRequest) -> InterviewResponse:
        if req.kind == "feedback":
            return await self._feedback(req)
        return await self._questions(req)

    # ── interview sub-flows ──────────────────────────────────────────────────

    async def _questions(self, req: InterviewRequest) -> InterviewResponse:
        payload = json.dumps(
            {
                "jobTitle": req.job_title,
                "jobDescription": req.job_description,
                "level": req.level,
            }
        )
        messages = [
            {"role": "system", "content": load_prompt("interview.txt")},
            {"role": "user", "content": payload},
        ]
        content = await self._ollama.chat(messages, json_mode=True)
        data = extract_json(content)
        # A model may return a bare list of questions instead of the wrapper object.
        if isinstance(data, list):
            data = {"questions": data}
        try:
            return InterviewResponse.model_validate(data)
        except ValidationError as exc:
            raise AiServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Model output failed validation: {exc.errors()}",
                502,
            ) from exc

    async def _feedback(self, req: InterviewRequest) -> InterviewResponse:
        if not req.answer or not req.answer.strip():
            raise AiServiceError(
                ErrorCode.BAD_REQUEST,
                "answer is required when kind is 'feedback'",
                400,
            )
        payload = json.dumps(
            {
                "jobTitle": req.job_title,
                "jobDescription": req.job_description,
                "level": req.level,
                "answer": req.answer,
            }
        )
        text = await self._chat_text(
            "interview_feedback.txt", payload, "interview feedback"
        )
        return InterviewResponse(feedback=text)

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _chat_text(self, prompt_file: str, payload: str, label: str) -> str:
        """Run a free-text generation and return non-empty stripped output."""
        messages = [
            {"role": "system", "content": load_prompt(prompt_file)},
            {"role": "user", "content": payload},
        ]
        content = await self._ollama.chat(messages, json_mode=False)
        text = (content or "").strip()
        if not text:
            raise AiServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Model returned an empty {label}",
                502,
            )
        return text
