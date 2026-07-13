"""Resume request/response schemas. Contract: BUILD_PLAN.md §4.1 / §4.2.

These response models also serve as the validation contract for Qwen's output:
if the model returns something that doesn't fit, validation fails and the service
raises INVALID_MODEL_OUTPUT.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from app.schemas.common import CamelModel, FileType


# ── /resume/parse ────────────────────────────────────────────────────────────


class ExperienceItem(CamelModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    highlights: list[str] = Field(default_factory=list)


class EducationItem(CamelModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    graduation_year: Optional[int] = None


class ParseRequest(CamelModel):
    text: str = Field(..., min_length=1)
    file_type: FileType


class ParseResponse(CamelModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    experiences: list[ExperienceItem] = Field(default_factory=list)
    educations: list[EducationItem] = Field(default_factory=list)


# ── /resume/score ────────────────────────────────────────────────────────────


class ScoreRequest(CamelModel):
    text: str = Field(..., min_length=1)
    target_role: Optional[str] = None


class ScoreResponse(CamelModel):
    ats_score: int
    quality_score: int
    breakdown: dict[str, int] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)
