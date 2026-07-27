"""Rerank request/response schemas.

The reranker re-scores a shortlist of documents (jobs) for fit to a query
(candidate). Quick LLM-based version: one listwise call scores every doc 0-1.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class RerankDocument(CamelModel):
    id: str
    text: str = Field(..., min_length=1)


class RerankRequest(CamelModel):
    query: str = Field(..., min_length=1)
    documents: list[RerankDocument] = Field(..., min_length=1)


class RerankScore(CamelModel):
    id: str
    score: float  # 0.0 - 1.0 relevance


class RerankResponse(CamelModel):
    scores: list[RerankScore]
