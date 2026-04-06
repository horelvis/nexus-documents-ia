"""
Multimodal Embedding Service

Provides unified embedding generation for text and visual content using
Qwen3-VL-Embedding-2B model via SGLang's OpenAI-compatible API.

Architecture (Unified Qwen3-VL):
    ┌────────────────────────────────────────┐
    │     MultimodalEmbeddingService         │
    │   (Qwen3-VL-Embedding-2B Primary)      │
    └─────────────────┬──────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   ┌────▼────┐  ┌────▼────┐  ┌────▼────────┐
   │  Text   │  │  Image  │  │ Multimodal  │
   │(Qwen3VL)│  │(Qwen3VL)│  │  (Qwen3VL)  │
   │   2B    │  │   2B    │  │  text+img   │
   └────┬────┘  └────┬────┘  └─────┬───────┘
        │            │             │
        └────────────┴─────────────┘
                     │
              ┌──────▼──────┐
              │  Weaviate   │
              │ (1024-dim)  │
              └─────────────┘

NOTE: TEI/bge-m3 is deprecated. Qwen3-VL-Embedding-2B now handles ALL embeddings
(text + images) in a unified vector space for optimal cross-modal retrieval.

Usage:
    from app.services.multimodal_embedding_service import multimodal_embedding_service

    # Text embedding (uses Qwen3-VL-Embedding-2B)
    text_vectors = await multimodal_embedding_service.embed_texts(["Hello world"])

    # Image embedding (uses Qwen3-VL-Embedding-2B)
    image_vectors = await multimodal_embedding_service.embed_images([image_bytes])

    # Multimodal embedding (uses Qwen3-VL with text+image combined)
    mm_vectors = await multimodal_embedding_service.embed_multimodal(
        texts=["A diagram showing..."],
        images=[diagram_bytes]
    )
"""

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from typing import List, Optional, Union

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ContentType(str, Enum):
    """Type of content to embed"""
    TEXT = "text"
    IMAGE = "image"
    TABLE_IMAGE = "table_image"
    DIAGRAM = "diagram"
    PAGE_THUMBNAIL = "page_thumbnail"
    MULTIMODAL = "multimodal"  # Combined text + image


@dataclass
class EmbeddingResult:
    """Result of embedding generation"""
    vectors: List[List[float]]
    content_type: ContentType
    model_used: str
    dimensions: int
    success: bool = True
    error: Optional[str] = None
    processing_time_ms: float = 0.0


@dataclass
class VisualContent:
    """Visual content item for embedding"""
    content_type: ContentType
    image_bytes: bytes
    caption: Optional[str] = None  # Text description for multimodal
    page_number: Optional[int] = None
    bbox: Optional[tuple] = None  # (x0, y0, x1, y1) in PDF coordinates
    metadata: dict = field(default_factory=dict)


class MultimodalEmbeddingService:
    """
    Service for generating embeddings from text, images, and multimodal content.

    PRIMARY PROVIDER: Qwen3-VL-Embedding-2B
    All embeddings (text, images, multimodal) use Qwen3-VL for unified vector space.
    This enables optimal cross-modal retrieval (text queries finding images and vice versa).

    Output: 1024-dimensional vectors stored in Weaviate.

    DEPRECATED: TEI/bge-m3 is kept for backwards compatibility but no longer used by default.
    """

    def __init__(self):
        self._tei_client: Optional[httpx.AsyncClient] = None  # Legacy, kept for fallback
        self._qwen_client: Optional[httpx.AsyncClient] = None  # Primary embedding client
        self._initialized = False

    async def _ensure_clients(self):
        """Initialize HTTP clients if not already done"""
        # Primary: Qwen3-VL-Embedding-2B client (always initialize)
        if self._qwen_client is None:
            self._qwen_client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0)  # Vision models need more time
            )

        # Legacy: TEI client (only initialize if explicitly needed)
        if self._tei_client is None:
            self._tei_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0)
            )

    async def close(self):
        """Close HTTP clients"""
        if self._tei_client:
            await self._tei_client.aclose()
            self._tei_client = None
        if self._qwen_client:
            await self._qwen_client.aclose()
            self._qwen_client = None

    @property
    def is_multimodal_enabled(self) -> bool:
        """Check if multimodal embedding is enabled"""
        return settings.multimodal_embedding_enabled

    async def embed_texts(
        self,
        texts: List[str],
        use_legacy_tei: bool = False,
    ) -> EmbeddingResult:
        """
        Generate embeddings for text content.

        By default uses Qwen3-VL-Embedding-2B for unified cross-modal vector space.
        Set use_legacy_tei=True to use deprecated TEI/bge-m3 (not recommended).

        Args:
            texts: List of text strings to embed
            use_legacy_tei: If True, use deprecated TEI instead of Qwen3-VL

        Returns:
            EmbeddingResult with vectors
        """
        import time
        start_time = time.time()

        await self._ensure_clients()

        if use_legacy_tei:
            # Legacy path: use TEI (deprecated)
            logger.warning("Using deprecated TEI embeddings. Consider using Qwen3-VL for unified vector space.")
            return await self._embed_texts_tei(texts, start_time)
        else:
            # Primary path: use Qwen3-VL for cross-modal compatibility
            return await self._embed_texts_qwen(texts, start_time)

    async def _embed_texts_tei(
        self,
        texts: List[str],
        start_time: float,
    ) -> EmbeddingResult:
        """Embed texts using TEI (bge-m3)"""
        import time

        try:
            response = await self._tei_client.post(
                f"{settings.tei_url}/embed",
                json={"inputs": texts}
            )

            if response.status_code == 200:
                vectors = response.json()
                return EmbeddingResult(
                    vectors=vectors,
                    content_type=ContentType.TEXT,
                    model_used=settings.embedding_model,
                    dimensions=len(vectors[0]) if vectors else settings.embedding_dimensions,
                    success=True,
                    processing_time_ms=(time.time() - start_time) * 1000,
                )
            else:
                logger.error(f"TEI error: {response.status_code} - {response.text}")
                return EmbeddingResult(
                    vectors=[],
                    content_type=ContentType.TEXT,
                    model_used=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                    success=False,
                    error=f"TEI error: {response.status_code}",
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

        except Exception as e:
            logger.error(f"TEI request failed: {e}")
            return EmbeddingResult(
                vectors=[],
                content_type=ContentType.TEXT,
                model_used=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                success=False,
                error=str(e),
                processing_time_ms=(time.time() - start_time) * 1000,
            )

    async def _embed_texts_qwen(
        self,
        texts: List[str],
        start_time: float,
    ) -> EmbeddingResult:
        """Embed texts using Qwen3-VL (for cross-modal compatibility)"""
        import time

        try:
            # SGLang OpenAI-compatible embeddings endpoint
            response = await self._qwen_client.post(
                f"{settings.multimodal_embedding_url}/embeddings",
                json={
                    "model": settings.multimodal_embedding_model,
                    "input": texts,
                }
            )

            if response.status_code == 200:
                data = response.json()
                vectors = [item["embedding"] for item in data["data"]]
                return EmbeddingResult(
                    vectors=vectors,
                    content_type=ContentType.TEXT,
                    model_used=settings.multimodal_embedding_model,
                    dimensions=len(vectors[0]) if vectors else settings.multimodal_embedding_dimensions,
                    success=True,
                    processing_time_ms=(time.time() - start_time) * 1000,
                )
            else:
                logger.error(f"Qwen3-VL error: {response.status_code} - {response.text}")
                return EmbeddingResult(
                    vectors=[],
                    content_type=ContentType.TEXT,
                    model_used=settings.multimodal_embedding_model,
                    dimensions=settings.multimodal_embedding_dimensions,
                    success=False,
                    error=f"Qwen3-VL error: {response.status_code}",
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

        except Exception as e:
            logger.error(f"Qwen3-VL text embedding failed: {e}")
            return EmbeddingResult(
                vectors=[],
                content_type=ContentType.TEXT,
                model_used=settings.multimodal_embedding_model,
                dimensions=settings.multimodal_embedding_dimensions,
                success=False,
                error=str(e),
                processing_time_ms=(time.time() - start_time) * 1000,
            )

    async def embed_images(
        self,
        images: List[Union[bytes, str]],
        content_type: ContentType = ContentType.IMAGE,
    ) -> EmbeddingResult:
        """
        Generate embeddings for images using Qwen3-VL.

        Args:
            images: List of image bytes or base64 strings
            content_type: Type of visual content (image, table_image, diagram, etc.)

        Returns:
            EmbeddingResult with vectors
        """
        import time
        start_time = time.time()

        if not settings.multimodal_embedding_enabled:
            logger.warning("Multimodal embedding not enabled, cannot embed images")
            return EmbeddingResult(
                vectors=[],
                content_type=content_type,
                model_used="none",
                dimensions=0,
                success=False,
                error="Multimodal embedding not enabled",
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        await self._ensure_clients()

        try:
            # Prepare image inputs as base64 data URLs
            image_inputs = []
            for img in images:
                if isinstance(img, bytes):
                    img_b64 = base64.b64encode(img).decode("utf-8")
                else:
                    img_b64 = img  # Already base64

                # Detect image format
                if img_b64.startswith("/9j/"):  # JPEG magic bytes in base64
                    mime_type = "image/jpeg"
                elif img_b64.startswith("iVBOR"):  # PNG magic bytes in base64
                    mime_type = "image/png"
                else:
                    mime_type = "image/png"  # Default

                image_inputs.append(f"data:{mime_type};base64,{img_b64}")

            # Use SGLang's vision embedding endpoint
            # Format: {"input": [{"type": "image_url", "image_url": {"url": data_url}}]}
            formatted_inputs = [
                {"type": "image_url", "image_url": {"url": url}}
                for url in image_inputs
            ]

            response = await self._qwen_client.post(
                f"{settings.multimodal_embedding_url}/embeddings",
                json={
                    "model": settings.multimodal_embedding_model,
                    "input": formatted_inputs,
                }
            )

            if response.status_code == 200:
                data = response.json()
                vectors = [item["embedding"] for item in data["data"]]
                return EmbeddingResult(
                    vectors=vectors,
                    content_type=content_type,
                    model_used=settings.multimodal_embedding_model,
                    dimensions=len(vectors[0]) if vectors else settings.multimodal_embedding_dimensions,
                    success=True,
                    processing_time_ms=(time.time() - start_time) * 1000,
                )
            else:
                logger.error(f"Qwen3-VL image error: {response.status_code} - {response.text}")
                return EmbeddingResult(
                    vectors=[],
                    content_type=content_type,
                    model_used=settings.multimodal_embedding_model,
                    dimensions=settings.multimodal_embedding_dimensions,
                    success=False,
                    error=f"Qwen3-VL error: {response.status_code}",
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

        except Exception as e:
            logger.error(f"Qwen3-VL image embedding failed: {e}")
            return EmbeddingResult(
                vectors=[],
                content_type=content_type,
                model_used=settings.multimodal_embedding_model,
                dimensions=settings.multimodal_embedding_dimensions,
                success=False,
                error=str(e),
                processing_time_ms=(time.time() - start_time) * 1000,
            )

    async def embed_multimodal(
        self,
        texts: List[str],
        images: List[Union[bytes, str]],
    ) -> EmbeddingResult:
        """
        Generate embeddings for multimodal content (text + images combined).

        Uses Qwen3-VL to create unified embeddings that capture both
        textual and visual information.

        Args:
            texts: List of text descriptions/captions
            images: List of image bytes or base64 strings (same length as texts)

        Returns:
            EmbeddingResult with vectors
        """
        import time
        start_time = time.time()

        if not settings.multimodal_embedding_enabled:
            logger.warning("Multimodal embedding not enabled")
            return EmbeddingResult(
                vectors=[],
                content_type=ContentType.MULTIMODAL,
                model_used="none",
                dimensions=0,
                success=False,
                error="Multimodal embedding not enabled",
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        if len(texts) != len(images):
            return EmbeddingResult(
                vectors=[],
                content_type=ContentType.MULTIMODAL,
                model_used=settings.multimodal_embedding_model,
                dimensions=settings.multimodal_embedding_dimensions,
                success=False,
                error="Number of texts must match number of images",
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        await self._ensure_clients()

        try:
            # Prepare multimodal inputs
            multimodal_inputs = []
            for text, img in zip(texts, images):
                if isinstance(img, bytes):
                    img_b64 = base64.b64encode(img).decode("utf-8")
                else:
                    img_b64 = img

                # Detect mime type
                if img_b64.startswith("/9j/"):
                    mime_type = "image/jpeg"
                elif img_b64.startswith("iVBOR"):
                    mime_type = "image/png"
                else:
                    mime_type = "image/png"

                # Combined text + image input
                multimodal_inputs.append([
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{img_b64}"}}
                ])

            response = await self._qwen_client.post(
                f"{settings.multimodal_embedding_url}/embeddings",
                json={
                    "model": settings.multimodal_embedding_model,
                    "input": multimodal_inputs,
                }
            )

            if response.status_code == 200:
                data = response.json()
                vectors = [item["embedding"] for item in data["data"]]
                return EmbeddingResult(
                    vectors=vectors,
                    content_type=ContentType.MULTIMODAL,
                    model_used=settings.multimodal_embedding_model,
                    dimensions=len(vectors[0]) if vectors else settings.multimodal_embedding_dimensions,
                    success=True,
                    processing_time_ms=(time.time() - start_time) * 1000,
                )
            else:
                logger.error(f"Qwen3-VL multimodal error: {response.status_code} - {response.text}")
                return EmbeddingResult(
                    vectors=[],
                    content_type=ContentType.MULTIMODAL,
                    model_used=settings.multimodal_embedding_model,
                    dimensions=settings.multimodal_embedding_dimensions,
                    success=False,
                    error=f"Qwen3-VL error: {response.status_code}",
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

        except Exception as e:
            logger.error(f"Qwen3-VL multimodal embedding failed: {e}")
            return EmbeddingResult(
                vectors=[],
                content_type=ContentType.MULTIMODAL,
                model_used=settings.multimodal_embedding_model,
                dimensions=settings.multimodal_embedding_dimensions,
                success=False,
                error=str(e),
                processing_time_ms=(time.time() - start_time) * 1000,
            )

    async def embed_visual_content(
        self,
        visual_contents: List[VisualContent],
    ) -> List[EmbeddingResult]:
        """
        Embed multiple visual content items with appropriate handling.

        Groups items by type and processes efficiently:
        - Images without captions: embed_images()
        - Images with captions: embed_multimodal()

        Args:
            visual_contents: List of VisualContent items

        Returns:
            List of EmbeddingResult, one per input
        """
        results = []

        # Group by whether they have captions
        image_only = []
        multimodal = []

        for vc in visual_contents:
            if vc.caption:
                multimodal.append(vc)
            else:
                image_only.append(vc)

        # Process image-only batch
        if image_only:
            images = [vc.image_bytes for vc in image_only]
            # Use the first content type (they should be similar in a batch)
            content_type = image_only[0].content_type
            result = await self.embed_images(images, content_type)

            # Split results back to individual items
            if result.success:
                for i, vec in enumerate(result.vectors):
                    results.append(EmbeddingResult(
                        vectors=[vec],
                        content_type=image_only[i].content_type,
                        model_used=result.model_used,
                        dimensions=result.dimensions,
                        success=True,
                        processing_time_ms=result.processing_time_ms / len(image_only),
                    ))
            else:
                for vc in image_only:
                    results.append(EmbeddingResult(
                        vectors=[],
                        content_type=vc.content_type,
                        model_used=result.model_used,
                        dimensions=result.dimensions,
                        success=False,
                        error=result.error,
                    ))

        # Process multimodal batch
        if multimodal:
            texts = [vc.caption for vc in multimodal]
            images = [vc.image_bytes for vc in multimodal]
            result = await self.embed_multimodal(texts, images)

            if result.success:
                for i, vec in enumerate(result.vectors):
                    results.append(EmbeddingResult(
                        vectors=[vec],
                        content_type=ContentType.MULTIMODAL,
                        model_used=result.model_used,
                        dimensions=result.dimensions,
                        success=True,
                        processing_time_ms=result.processing_time_ms / len(multimodal),
                    ))
            else:
                for vc in multimodal:
                    results.append(EmbeddingResult(
                        vectors=[],
                        content_type=ContentType.MULTIMODAL,
                        model_used=result.model_used,
                        dimensions=result.dimensions,
                        success=False,
                        error=result.error,
                    ))

        return results

    async def health_check(self) -> dict:
        """Check health of embedding services"""
        await self._ensure_clients()

        status = {
            "qwen3_vl": {
                "primary": True,
                "healthy": False,
                "model": settings.embedding_model,
                "url": settings.embedding_url,
            },
            "tei": {
                "primary": False,
                "deprecated": True,
                "healthy": False,
                "model": "BAAI/bge-m3",
                "url": settings.tei_url,
            },
        }

        # Check Qwen3-VL (PRIMARY)
        try:
            # SGLang health endpoint is at /health (not /v1/health)
            base_url = settings.embedding_url.replace("/v1", "")
            response = await self._qwen_client.get(
                f"{base_url}/health",
                timeout=5.0
            )
            status["qwen3_vl"]["healthy"] = response.status_code == 200
        except Exception as e:
            status["qwen3_vl"]["error"] = str(e)

        # Check TEI (DEPRECATED - optional)
        try:
            response = await self._tei_client.get(
                f"{settings.tei_url}/health",
                timeout=5.0
            )
            status["tei"]["healthy"] = response.status_code == 200
        except Exception as e:
            # TEI failure is not critical since it's deprecated
            status["tei"]["error"] = str(e)
            status["tei"]["note"] = "TEI is deprecated, failure is non-critical"

        return status


# Global singleton instance
multimodal_embedding_service = MultimodalEmbeddingService()
