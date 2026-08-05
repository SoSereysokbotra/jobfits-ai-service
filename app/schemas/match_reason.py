"""Match-reasoning request/response schemas (Phase C).

Structured "why does this candidate fit this job" output. Unlike /rerank (one
number per job), this returns the *reasoning*: which requirements are met, with
the CV evidence for each, and which are gaps. The `evidenceFromCv` strings are
what the faithfulness metric checks against the real CV text, so they must be
quotes from the input — never model prose.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel

Verdict = Literal["strong", "possible", "weak"]


class MatchReasonRequest(CamelModel):
    candidate_summary: str = Field(..., min_length=1)
    job_title: str = Field(..., min_length=1)
    job_description: str = Field(..., min_length=1)
    # Prompt A/B knob for the Phase C flywheel: picks app/prompts/match_reason_<v>.txt.
    prompt_version: str = Field(default="v1", pattern=r"^[a-z0-9_]+$")


class MatchedRequirement(CamelModel):
    requirement: str
    evidence_from_cv: str


class Gap(CamelModel):
    requirement: str
    note: str


class MatchReasonResponse(CamelModel):
    fit_score: float = Field(..., ge=0.0, le=1.0)
    matched_requirements: list[MatchedRequirement] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    verdict: Verdict
    prompt_version: str = "v1"
    # True when the LLM failed twice and the deterministic fallback produced this
    # response. Evals must report degraded rows separately instead of scoring them
    # as model judgement.
    degraded: bool = False
