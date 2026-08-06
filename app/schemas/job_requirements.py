"""Job requirement extraction schemas.

Pulls the checkable requirements out of a free-text job description so the backend can
compare them against a candidate's parsed résumé.

This is the one place an LLM genuinely earns its keep in the skill-gap feature: where a job
already carries a structured `requirements` list, comparing it to CV skills is deterministic
string work and needs no model. Reading requirements OUT of prose is the part that does —
and it is the capability Phase C measured at 87.7-89.2% groundedness.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class JobRequirementsRequest(CamelModel):
    job_title: str = Field(..., min_length=1)
    job_description: str = Field(..., min_length=1)
    # Picks app/prompts/job_requirements_<v>.txt.
    prompt_version: str = Field(default="v1", pattern=r"^[a-z0-9_]+$")


class JobRequirementsResponse(CamelModel):
    # Grounded requirements ONLY — anything built from words the posting never used is
    # dropped before it gets here. Empty is a valid answer: a posting that states no
    # checkable requirement should yield none rather than a padded list.
    requirements: list[str] = Field(default_factory=list)
    prompt_version: str = "v1"
    # Fraction of the model's RAW output that was grounded, measured before filtering, so
    # this keeps reporting model quality rather than the quality of our filtering. A
    # falling value means extraction is drifting into invention.
    groundedness: float = 0.0
    # How many invented requirements were removed. Measured non-zero on real postings:
    # the model produced "Experience with Docker and Kubernetes" for a welding job.
    dropped_ungrounded: int = 0
