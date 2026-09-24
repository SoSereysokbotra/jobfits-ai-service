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
    # A photographed or scanned CV, whose text the backend obtained by OCR before
    # calling here. Added 2026-09-24: without it the backend's OCR path fails at this
    # boundary with a 422, because this field is VALIDATED here and then never read —
    # ResumeService.parse uses only `text` and `prompt_version`. It is kept rather than
    # dropped so the request still records what the text came from.
    IMAGE = "IMAGE"


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
