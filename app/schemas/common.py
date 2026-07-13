"""Shared pydantic types.

The backend speaks camelCase (fileType, fullName, atsScore, ...). `CamelModel`
generates camelCase aliases automatically while still accepting snake_case, and
FastAPI serializes responses by alias, so the wire format matches the contract.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model: camelCase on the wire, snake_case in Python."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class FileType(str, Enum):
    PDF = "PDF"
    DOCX = "DOCX"


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
