"""
Client for the text extraction microservice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings


@dataclass
class TextExtractionResult:
    """Structured result returned by the text extraction microservice."""

    text: str
    language: Optional[str]
    metadata: Dict[str, Any]
    characters: int


class TextExtractionClient:
    """HTTP client wrapper for the text extraction microservice."""

    def __init__(self, tenant_id: str, user_id: Optional[str] = None) -> None:
        self.base_url = (settings.TEXT_EXTRACTION_SERVICE_URL or "").rstrip("/")
        if not self.base_url:
            raise ValueError("TEXT_EXTRACTION_SERVICE_URL is not configured")

        self.api_key = settings.MICROSERVICES_API_KEY
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.timeout = httpx.Timeout(120.0, connect=10.0)

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

        headers = {
            "X-API-Key": self.api_key,
            "X-Tenant-ID": self.tenant_id,
        }
        if self.user_id:
            headers["X-User-ID"] = self.user_id

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

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/text-extraction/extract",
                headers=headers,
                files=files,
                data=data,
            )
            response.raise_for_status()
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
