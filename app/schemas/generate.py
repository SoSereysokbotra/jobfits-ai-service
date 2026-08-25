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
    # Optional: some callers only hold identifiers. The browser extension must
    # never scrape a posting's body (LinkedIn TOS), so it sends title + company
    # only and the prompt degrades to resume-led writing. See prompts/cover_letter.txt.
    job_description: Optional[str] = None
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
    # MUST accept "". The browser extension reads a job title off the page and has no
    # posting body, so `GenerationService.interviewForExternalJob` sends an empty
    # description by design.
    #
    # FOUND 2026-08-20 — this was `min_length=1`, so every extension interview-prep
    # request was rejected 400, the backend swallowed it as an AiServiceError, and users
    # silently got the three hardcoded static questions instead of generated ones. The
    # feature had never once run on a model. A title-only request is the normal case here,
    # not a malformed one.
    job_description: str = Field(default="", min_length=0)
    level: str = Field(..., min_length=1)
    kind: Literal["questions", "feedback"]
    answer: Optional[str] = None  # required when kind == "feedback"


class InterviewResponse(CamelModel):
    questions: list[InterviewQuestion] = Field(default_factory=list)
    feedback: Optional[str] = None
