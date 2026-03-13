"""Schemas for document conversion."""

from pydantic import BaseModel


class ConvertResponse(BaseModel):
    size_bytes: int
    content_type: str = "application/pdf"
