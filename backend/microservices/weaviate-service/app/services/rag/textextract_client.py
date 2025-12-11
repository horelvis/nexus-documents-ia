"""
TextExtract Service Client

HTTP client for calling the textextract-service to extract text from documents.
Used by the RAG pipeline before applying DocumentIntelligence and chunking.

Usage:
    from app.services.rag.textextract_client import textextract_client

    result = await textextract_client.extract_from_bytes(
        file_bytes=pdf_content,
        filename="contract.pdf",
        tenant_id="tenant-123",
    )

    if result.success:
        text = result.text
        # Apply DocumentIntelligence, chunking, etc.
"""

import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


@dataclass
class TextExtractResult:
    """Result from textextract-service"""
    success: bool
    text: str
    characters: int
    language: Optional[str]
    metadata: Dict[str, Any]
    error: Optional[str] = None

    @classmethod
    def from_response(cls, data: Dict[str, Any]) -> "TextExtractResult":
        return cls(
            success=data.get("success", False),
            text=data.get("text", ""),
            characters=data.get("characters", 0),
            language=data.get("language"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def error_result(cls, error: str) -> "TextExtractResult":
        return cls(
            success=False,
            text="",
            characters=0,
            language=None,
            metadata={},
            error=error,
        )


class TextExtractClient:
    """
    HTTP client for textextract-service.

    Handles authentication and provides async methods for text extraction.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
    ):
        self.base_url = base_url or os.environ.get(
            "TEXT_EXTRACTION_SERVICE_URL",
            "http://textextract-service:8000"
        )
        self.api_key = api_key or os.environ.get("MICROSERVICES_API_KEY", "")
        self.timeout = timeout

    async def extract_from_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        strategy: str = "auto",
    ) -> TextExtractResult:
        """
        Extract text from file bytes.

        Args:
            file_bytes: Raw file content
            filename: Original filename (used for extension detection)
            tenant_id: Tenant identifier for logging
            user_id: User identifier for logging
            strategy: Extraction strategy (auto, fast, hi_res)

        Returns:
            TextExtractResult with extracted text or error
        """
        url = f"{self.base_url}/api/v1/text-extraction/extract"

        headers = {
            "X-API-Key": self.api_key,
        }
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        if user_id:
            headers["X-User-ID"] = user_id

        files = {
            "file": (filename, file_bytes),
        }
        data = {
            "strategy": strategy,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"Calling textextract-service for {filename}")

                response = await client.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                )

                if response.status_code == 200:
                    result = TextExtractResult.from_response(response.json())
                    logger.info(
                        f"Text extraction successful: {result.characters} chars, "
                        f"language={result.language}"
                    )
                    return result
                else:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = error_json.get("detail", response.text)
                    except Exception:
                        pass

                    logger.error(
                        f"Text extraction failed: {response.status_code} - {error_detail}"
                    )
                    return TextExtractResult.error_result(
                        f"Extraction failed: {response.status_code} - {error_detail}"
                    )

        except httpx.TimeoutException:
            logger.error(f"Text extraction timeout for {filename}")
            return TextExtractResult.error_result("Extraction timeout")
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to textextract-service: {e}")
            return TextExtractResult.error_result(f"Connection error: {e}")
        except Exception as e:
            logger.error(f"Text extraction error: {e}")
            return TextExtractResult.error_result(str(e))

    async def extract_from_url(
        self,
        file_url: str,
        filename: str,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        strategy: str = "auto",
    ) -> TextExtractResult:
        """
        Download file from URL and extract text.

        Args:
            file_url: URL to download file from
            filename: Filename for extension detection
            tenant_id: Tenant identifier
            user_id: User identifier
            strategy: Extraction strategy

        Returns:
            TextExtractResult with extracted text or error
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info(f"Downloading file from {file_url}")
                response = await client.get(file_url)

                if response.status_code != 200:
                    return TextExtractResult.error_result(
                        f"Failed to download file: {response.status_code}"
                    )

                file_bytes = response.content

            return await self.extract_from_bytes(
                file_bytes=file_bytes,
                filename=filename,
                tenant_id=tenant_id,
                user_id=user_id,
                strategy=strategy,
            )

        except Exception as e:
            logger.error(f"Error downloading/extracting from URL: {e}")
            return TextExtractResult.error_result(str(e))

    async def health_check(self) -> Dict[str, Any]:
        """Check textextract-service health"""
        url = f"{self.base_url}/api/v1/text-extraction/health"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers={"X-API-Key": self.api_key},
                )

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        **response.json(),
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"Status {response.status_code}",
                    }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }


# Global instance
textextract_client = TextExtractClient()
