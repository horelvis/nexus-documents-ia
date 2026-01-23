"""
OCR Service Client

HTTP client for calling the textextract-service's OCR endpoint
for enhanced OCR processing of scanned PDFs.

This client is used as a fallback when standard text extraction
produces low-quality results (detected by DocumentIntelligence).

Usage:
    from app.services.rag.ocr_client import ocr_client

    result = await ocr_client.extract_with_ocr(
        file_bytes=pdf_content,
        languages=["es", "en"],
    )

    if result.success and result.confidence > 0.6:
        text = result.text
"""

import os
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import httpx

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Result from OCR extraction"""
    success: bool
    text: str
    confidence: float  # 0.0 - 1.0
    engine: str  # easyocr, tesseract, hybrid
    languages: List[str]
    page_count: int
    processing_time_ms: float
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @classmethod
    def from_response(cls, data: Dict[str, Any]) -> "OCRResult":
        return cls(
            success=bool(data.get("text", "").strip()),
            text=data.get("text", ""),
            confidence=data.get("confidence", 0.0),
            engine=data.get("engine", "unknown"),
            languages=data.get("languages", []),
            page_count=data.get("page_count", 0),
            processing_time_ms=data.get("processing_time_ms", 0.0),
            warnings=data.get("warnings", []),
        )

    @classmethod
    def error_result(cls, error: str) -> "OCRResult":
        return cls(
            success=False,
            text="",
            confidence=0.0,
            engine="none",
            languages=[],
            page_count=0,
            processing_time_ms=0.0,
            warnings=[],
            error=error,
        )


class OCRClient:
    """
    HTTP client for textextract-service OCR endpoint.

    Used when DocumentIntelligence detects that standard text
    extraction produced low-quality results.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 300.0,  # OCR can be slow
    ):
        self.base_url = base_url or os.environ.get(
            "TEXT_EXTRACTION_SERVICE_URL",
            "http://textextract-service:8000"
        )
        self.api_key = api_key or os.environ.get("MICROSERVICES_API_KEY", "")
        self.timeout = timeout

    async def extract_with_ocr(
        self,
        file_bytes: bytes,
        languages: Optional[List[str]] = None,
        use_hybrid: bool = False,
        preprocess: bool = True,
        dpi: int = 300,
        tenant_id: Optional[str] = None,
    ) -> OCRResult:
        """
        Extract text using enhanced OCR.

        Args:
            file_bytes: PDF or image file content
            languages: OCR languages (default: ["es", "en"])
            use_hybrid: Use both EasyOCR and Tesseract
            preprocess: Apply image preprocessing
            dpi: DPI for PDF conversion
            tenant_id: Tenant identifier for logging

        Returns:
            OCRResult with extracted text and confidence
        """
        url = f"{self.base_url}/api/v1/text-extraction/ocr"

        headers = {
            "X-API-Key": self.api_key,
        }
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id

        files = {
            "file": ("document.pdf", file_bytes),
        }
        data = {
            "languages": ",".join(languages or ["es", "en"]),
            "use_hybrid": str(use_hybrid).lower(),
            "preprocess": str(preprocess).lower(),
            "dpi": str(dpi),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(
                    f"Calling OCR service: languages={languages}, hybrid={use_hybrid}, dpi={dpi}"
                )

                response = await client.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                )

                if response.status_code == 200:
                    result = OCRResult.from_response(response.json())
                    logger.info(
                        f"OCR extraction successful: {len(result.text)} chars, "
                        f"confidence={result.confidence:.2f}, engine={result.engine}"
                    )
                    return result
                else:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = error_json.get("detail", response.text)
                    except Exception:
                        pass

                    logger.error(f"OCR extraction failed: {response.status_code} - {error_detail}")
                    return OCRResult.error_result(
                        f"OCR failed: {response.status_code} - {error_detail}"
                    )

        except httpx.TimeoutException:
            logger.error("OCR extraction timeout")
            return OCRResult.error_result("OCR timeout")
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to OCR service: {e}")
            return OCRResult.error_result(f"Connection error: {e}")
        except Exception as e:
            logger.error(f"OCR extraction error: {e}")
            return OCRResult.error_result(str(e))

    async def health_check(self) -> Dict[str, Any]:
        """Check OCR service health"""
        url = f"{self.base_url}/api/v1/text-extraction/ocr/health"

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
ocr_client = OCRClient()
