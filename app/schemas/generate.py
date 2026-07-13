"""Generation request/response schemas. Contract: BUILD_PLAN.md §4.4 / §4.5."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.schemas.common import CamelModel


# ── /generate/cover-letter ───────────────────────────────────────────────────


class CoverLetterRequest(CamelModel):
    resume_summary: str = Field(..., min_length=1)
    job_title: str = Field(..., min_length=1)
    company_name: str = Field(..., min_length=1)
    job_description: str = Field(..., min_length=1)
    tone: str = "professional"


class CoverLetterResponse(CamelModel):
    cover_letter: str


# ── /generate/interview ──────────────────────────────────────────────────────


class InterviewQuestion(CamelModel):
    question: str
    category: str
    guidance: str


class InterviewRequest(CamelModel):
    job_title: str = Field(..., min_length=1)
    job_description: str = Field(..., min_length=1)
    level: str = Field(..., min_length=1)
    kind: Literal["questions", "feedback"]
    answer: Optional[str] = None  # required when kind == "feedback"


class InterviewResponse(CamelModel):
    questions: list[InterviewQuestion] = Field(default_factory=list)
    feedback: Optional[str] = None
