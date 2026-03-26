"""HTTP client for intelligence-docs-service.

Provides extraction, embedding, entity extraction, and classification
via the unified intelligence-docs-service. Returns dataclasses compatible
with the previous extraction client interfaces to
minimize changes in the indexing pipeline.
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("INTELLIGENCE_DOCS_SERVICE_URL", "http://intelligence-docs-service:8000")
_TIMEOUT_EXTRACT = float(os.getenv("INTELLIGENCE_EXTRACT_TIMEOUT", "600"))
_TIMEOUT_EMBED = float(os.getenv("INTELLIGENCE_EMBED_TIMEOUT", "30"))
_TIMEOUT_ENTITY = float(os.getenv("INTELLIGENCE_ENTITY_TIMEOUT", "60"))

# ---------------------------------------------------------------------------
# Pooled HTTP client singleton — reuses TCP connections across calls
# ---------------------------------------------------------------------------

_http_client: Optional[httpx.AsyncClient] = None
_http_lock = asyncio.Lock()


async def _get_client() -> httpx.AsyncClient:
    """Get or create the shared httpx client with connection pooling."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    async with _http_lock:
        if _http_client is not None and not _http_client.is_closed:
            return _http_client
        _http_client = httpx.AsyncClient(
            base_url=_BASE_URL,
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
            follow_redirects=True,
        )
        logger.info(f"🔌 Intelligence client pool created → {_BASE_URL}")
        return _http_client


async def close_client() -> None:
    """Close the shared client (call on app shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


# ---------------------------------------------------------------------------
# Result dataclasses (compatible with old clients)
# ---------------------------------------------------------------------------

@dataclass
class TextExtractResult:
    """Result dataclass for intelligence-docs-service text extraction."""
    success: bool
    text: str
    characters: int
    language: Optional[str]
    metadata: Dict[str, Any]
    error: Optional[str] = None

    @classmethod
    def error_result(cls, error: str) -> "TextExtractResult":
        return cls(success=False, text="", characters=0, language=None, metadata={}, error=error)


@dataclass
class LangExtractResult:
    """Drop-in replacement for langextract_client.LangExtractResult."""
    success: bool
    entities: List[Dict[str, Any]] = field(default_factory=list)
    document_type: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def error_result(cls, error: str) -> "LangExtractResult":
        return cls(success=False, error=error)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

async def extract_from_bytes(
    file_bytes: bytes,
    filename: str,
    tenant_id: str = "",
    user_id: str = "",
    strategy: str = "auto",
) -> TextExtractResult:
    """Extract text from file bytes via intelligence-docs-service."""
    try:
        client = await _get_client()
        response = await client.post(
            "/extract",
            files={"file": (filename, file_bytes)},
            data={"filename": filename},
            timeout=_TIMEOUT_EXTRACT,
        )
        response.raise_for_status()
        data = response.json()

        return TextExtractResult(
            success=True,
            text=data.get("text", ""),
            characters=len(data.get("text", "")),
            language=data.get("language"),
            metadata=data.get("metadata", {}),
        )
    except Exception as e:
        logger.error(f"Intelligence extraction failed: {e}")
        return TextExtractResult.error_result(str(e))


async def extract_from_url(
    file_url: str,
    filename: str,
    tenant_id: str = "",
    user_id: str = "",
    strategy: str = "auto",
) -> TextExtractResult:
    """Extract text from URL via intelligence-docs-service."""
    try:
        client = await _get_client()
        response = await client.post(
            "/extract",
            data={"url": file_url, "filename": filename},
            timeout=_TIMEOUT_EXTRACT,
        )
        response.raise_for_status()
        data = response.json()

        return TextExtractResult(
            success=True,
            text=data.get("text", ""),
            characters=len(data.get("text", "")),
            language=data.get("language"),
            metadata=data.get("metadata", {}),
        )
    except Exception as e:
        logger.error(f"Intelligence URL extraction failed: {e}")
        return TextExtractResult.error_result(str(e))


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

async def embed(text: str, task: str = "") -> Optional[List[float]]:
    """Generate embedding for a single text."""
    try:
        client = await _get_client()
        response = await client.post(
            "/embed",
            json={"text": text, "task": task},
            timeout=_TIMEOUT_EMBED,
        )
        response.raise_for_status()
        return response.json()["embedding"]
    except Exception as e:
        logger.warning(f"Intelligence embedding failed: {e}")
        return None


async def embed_batch(texts: List[str], task: str = "") -> Optional[List[List[float]]]:
    """Generate embeddings for multiple texts."""
    try:
        client = await _get_client()
        response = await client.post(
            "/embed",
            json={"texts": texts, "task": task},
            timeout=_TIMEOUT_EMBED,
        )
        response.raise_for_status()
        return response.json()["embeddings"]
    except Exception as e:
        logger.warning(f"Intelligence batch embedding failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

async def extract_entities(
    text: str,
    document_type: str = "general",
    filename: Optional[str] = None,
    use_llm: bool = True,
    language: str = "es",
) -> LangExtractResult:
    """Extract entities via intelligence-docs-service."""
    try:
        client = await _get_client()
        response = await client.post(
            "/entities",
            json={"text": text, "language": language, "document_type": document_type},
            timeout=_TIMEOUT_ENTITY,
        )
        response.raise_for_status()
        data = response.json()

        entities = [
            {
                "type": e["type"],
                "value": e["value"],
                "provider": e.get("provider", "unknown"),
                "confidence": e.get("confidence", 0.8),
                "start_pos": e.get("start_pos"),
                "end_pos": e.get("end_pos"),
                "attributes": e.get("attributes", {}),
            }
            for e in data.get("entities", [])
        ]
        return LangExtractResult(success=True, entities=entities)
    except Exception as e:
        logger.warning(f"Intelligence entity extraction failed: {e}")
        return LangExtractResult.error_result(str(e))


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

async def classify(text: str, filename: str) -> Optional[Dict[str, Any]]:
    """Classify document type."""
    try:
        client = await _get_client()
        response = await client.post(
            "/classify",
            json={"text": text[:2000], "filename": filename},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Intelligence classification failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Health / dimensions
# ---------------------------------------------------------------------------

_cached_dimensions: Optional[int] = None


async def get_embedding_dimensions() -> Optional[int]:
    """Get embedding dimensions from health endpoint (cached)."""
    global _cached_dimensions
    if _cached_dimensions is not None:
        return _cached_dimensions
    try:
        client = await _get_client()
        response = await client.get("/health", timeout=10.0)
        response.raise_for_status()
        data = response.json()
        for p in data.get("providers", {}).get("embedding", []):
            if p.get("available") and p.get("dimensions"):
                _cached_dimensions = p["dimensions"]
                return _cached_dimensions
    except Exception as e:
        logger.warning(f"Failed to get embedding dimensions: {e}")
    return None


# ---------------------------------------------------------------------------
# Adapter class (drop-in for TextExtractClient usage in indexing pipeline)
# ---------------------------------------------------------------------------

@dataclass
class OCRResult:
    """Result from OCR extraction — compatible with the old ocr_client.OCRResult interface."""
    success: bool
    text: str
    confidence: float  # 0.0 – 1.0
    engine: str        # glm_ocr, docling, tika, unknown
    languages: List[str]
    page_count: int
    processing_time_ms: float
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @classmethod
    def from_text_extract(cls, result: "TextExtractResult", elapsed_ms: float) -> "OCRResult":
        """Build an OCRResult from a TextExtractResult (intelligence-docs /extract response)."""
        engine = result.metadata.get("provider", result.metadata.get("extractor", "unknown"))
        confidence = result.metadata.get("confidence", 0.8 if result.success else 0.0)
        page_count = result.metadata.get("page_count", 0)
        languages = [result.language] if result.language else []
        return cls(
            success=result.success and bool(result.text.strip()),
            text=result.text,
            confidence=float(confidence),
            engine=str(engine),
            languages=languages,
            page_count=int(page_count),
            processing_time_ms=elapsed_ms,
            warnings=[],
            error=result.error,
        )

    @classmethod
    def error_result(cls, error: str) -> "OCRResult":
        return cls(
            success=False, text="", confidence=0.0, engine="none",
            languages=[], page_count=0, processing_time_ms=0.0,
            warnings=[], error=error,
        )


class IntelligenceExtractClient:
    """Drop-in replacement for TextExtractClient in the indexing pipeline."""

    async def extract_from_bytes(self, file_bytes, filename, tenant_id="", user_id="", strategy="auto"):
        return await extract_from_bytes(file_bytes, filename, tenant_id, user_id, strategy)

    async def extract_from_url(self, file_url, filename, tenant_id="", user_id="", strategy="auto"):
        return await extract_from_url(file_url, filename, tenant_id, user_id, strategy)

    async def extract_with_ocr(
        self,
        file_bytes: bytes,
        languages: Optional[List[str]] = None,
        use_hybrid: bool = False,
        preprocess: bool = True,
        dpi: int = 300,
        tenant_id: str = "",
    ) -> "OCRResult":
        """OCR fallback via intelligence-docs-service /extract endpoint.

        Intelligence-docs-service auto-routes to GLM-OCR
        when available; otherwise falls through to Docling / Tika.
        """
        import time as _time
        start = _time.time()
        try:
            result = await extract_from_bytes(
                file_bytes=file_bytes,
                filename="document.pdf",
                tenant_id=tenant_id,
                strategy="auto",
            )
            elapsed = (_time.time() - start) * 1000
            return OCRResult.from_text_extract(result, elapsed)
        except Exception as e:
            logger.error(f"OCR via intelligence-docs failed: {e}")
            return OCRResult.error_result(str(e))

    async def health_check(self):
        try:
            client = await _get_client()
            resp = await client.get("/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


# Singleton instance for pipeline injection
intelligence_extract_client = IntelligenceExtractClient()
