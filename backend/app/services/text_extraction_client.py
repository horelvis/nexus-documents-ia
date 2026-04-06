"""
Client for the text extraction microservice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.clients.base import BaseHTTPClient
from app.core.config import settings


@dataclass
class TextExtractionResult:
    """Structured result returned by the text extraction microservice."""

    text: str
    language: Optional[str]
    metadata: Dict[str, Any]
    characters: int


class TextExtractionClient(BaseHTTPClient):
    """HTTP client wrapper for the text extraction microservice."""

    def __init__(self, tenant_id: str, user_id: Optional[str] = None) -> None:
        self.base_url = (settings.TEXT_EXTRACTION_SERVICE_URL or "").rstrip("/")
        if not self.base_url:
            raise ValueError("TEXT_EXTRACTION_SERVICE_URL is not configured")

        self.tenant_id = tenant_id
        self.user_id = user_id
        super().__init__(
            service_name="text-extraction",
            base_url=self.base_url,
            timeout_type="document",
        )

    async def extract_text(
        self,
        file_bytes: bytes,
        filename: str,
        file_extension: str,
        strategy: str | None = None,
    ) -> TextExtractionResult:
        """
        Send a document to the text extraction microservice and return the extracted content.
        """
        if not file_bytes:
            raise ValueError("File bytes cannot be empty")

        strategy_value = strategy or settings.TEXT_EXTRACTION_DEFAULT_STRATEGY

        files = {
            "file": (
                filename or f"document{file_extension or ''}",
                file_bytes,
                "application/octet-stream",
            )
        }
        data = {
            "strategy": strategy_value,
        }

        response = await self.request(
            "POST",
            "/extract",
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            files=files,
            data=data,
        )
        payload = response.json()

        text = payload.get("text") or ""
        metadata = payload.get("metadata") or {}
        language = payload.get("language")
        characters = payload.get("characters", len(text))

        return TextExtractionResult(
            text=text,
            language=language,
            metadata=metadata,
            characters=characters,
        )
