"""
Few-Shot Retriever — Retrieves Q&A examples via the Main API.

Replaces the old pgvector-based retriever.  The Main API (backend)
still stores few-shot examples in PostgreSQL and exposes them via
REST endpoints.  This retriever calls those endpoints instead of
querying pgvector directly.

Usage:
    retriever = get_few_shot_retriever()
    examples = await retriever.search("Cuantos dias de preaviso para despido?", limit=3)
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.schemas.prompts import FewShotDomain

logger = logging.getLogger(__name__)


@dataclass
class FewShotExample:
    """A few-shot example with similarity score."""
    id: UUID
    question: str
    answer: str
    category: Optional[str] = None
    domain: Optional[str] = None
    tags: Optional[List[str]] = None
    quality_score: float = 1.0
    similarity_score: float = 0.0


class FewShotRetriever:
    """
    Retriever for few-shot examples via Main API HTTP endpoints.

    The Main API stores examples in PostgreSQL (with optional pgvector
    similarity).  This retriever delegates entirely to those endpoints,
    removing the need for a direct database connection from emma-agent-service.
    """

    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None
        self._embedding_cache: Dict[str, List[float]] = {}
        self._cache_max_size = 100

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text using weaviate-service."""
        cache_key = text[:200]
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        try:
            client = await self._get_http_client()
            response = await client.post(
                f"{settings.weaviate_service_url}/embed",
                json={"text": text, "task": "retrieval.query"},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )

            if response.status_code == 200:
                data = response.json()
                embedding = data.get("embedding")
                if embedding:
                    if len(self._embedding_cache) >= self._cache_max_size:
                        self._embedding_cache.pop(next(iter(self._embedding_cache)))
                    self._embedding_cache[cache_key] = embedding
                    return embedding

            logger.warning(f"Failed to get embedding: {response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return None

    async def search(
        self,
        query: str,
        *,
        limit: int = 3,
        tenant_id: Optional[UUID] = None,
        domain: Optional[FewShotDomain] = None,
        category: Optional[str] = None,
        min_quality_score: float = 0.5,
        min_similarity: Optional[float] = None,
    ) -> List[FewShotExample]:
        """
        Search for similar few-shot examples via the Main API.

        Gets an embedding from weaviate-service, then sends it to the
        Main API's /prompts/few-shot/search endpoint which performs
        the pgvector similarity search in the backend database.
        """
        if not settings.few_shot_enabled:
            return []

        if min_similarity is None:
            min_similarity = settings.few_shot_min_similarity

        start_time = time.time()

        # Get embedding for query
        embedding = await self._get_embedding(query)
        if embedding is None:
            logger.warning("Could not get embedding for query, trying keyword fallback")
            return await self._fallback_search(query, limit, tenant_id, domain, category, min_quality_score)

        try:
            client = await self._get_http_client()
            headers = {
                "X-API-Key": settings.MICROSERVICES_API_KEY,
            }
            if tenant_id:
                headers["X-Tenant-ID"] = str(tenant_id)

            params: Dict[str, Any] = {"limit": limit * 2}
            if domain:
                params["domain"] = domain.value if hasattr(domain, "value") else str(domain)
            if category:
                params["category"] = category
            params["min_quality_score"] = min_quality_score

            response = await client.post(
                f"{settings.api_url}/api/v1/prompts/few-shot/search",
                params=params,
                json={"query_text": query, "embedding": embedding},
                headers=headers,
            )

            if response.status_code != 200:
                logger.warning(f"Few-shot search API returned {response.status_code}")
                return await self._fallback_search(query, limit, tenant_id, domain, category, min_quality_score)

            rows = response.json()
            examples = []
            for row in rows:
                similarity = row.get("similarity_score", 0.0) or 0.0
                if similarity < min_similarity:
                    continue

                examples.append(FewShotExample(
                    id=UUID(row["id"]),
                    question=row["question"],
                    answer=row["answer"],
                    category=row.get("category"),
                    domain=row.get("domain"),
                    tags=row.get("tags"),
                    quality_score=row.get("quality_score", 1.0),
                    similarity_score=similarity,
                ))

                if len(examples) >= limit:
                    break

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Few-shot search via API: found {len(examples)} examples "
                f"(query_len={len(query)}, time={elapsed_ms:.1f}ms)"
            )

            return examples

        except Exception as e:
            logger.error(f"Few-shot search failed: {e}")
            return await self._fallback_search(
                query, limit, tenant_id, domain, category, min_quality_score
            )

    async def _fallback_search(
        self,
        query: str,
        limit: int,
        tenant_id: Optional[UUID],
        domain: Optional[FewShotDomain],
        category: Optional[str],
        min_quality_score: float,
    ) -> List[FewShotExample]:
        """Fallback: list examples from Main API (no vector search, sorted by quality)."""
        try:
            client = await self._get_http_client()
            headers = {
                "X-API-Key": settings.MICROSERVICES_API_KEY,
            }
            if tenant_id:
                headers["X-Tenant-ID"] = str(tenant_id)

            params: Dict[str, Any] = {
                "limit": limit,
                "active_only": True,
            }
            if domain:
                params["domain"] = domain.value if hasattr(domain, "value") else str(domain)
            if category:
                params["category"] = category

            response = await client.get(
                f"{settings.api_url}/api/v1/prompts/few-shot",
                params=params,
                headers=headers,
            )

            if response.status_code != 200:
                logger.warning(f"Few-shot fallback API returned {response.status_code}")
                return []

            rows = response.json()
            examples = []
            for row in rows:
                if (row.get("quality_score", 0) or 0) < min_quality_score:
                    continue
                examples.append(FewShotExample(
                    id=UUID(row["id"]),
                    question=row["question"],
                    answer=row["answer"],
                    category=row.get("category"),
                    domain=row.get("domain"),
                    tags=row.get("tags"),
                    quality_score=row.get("quality_score", 1.0),
                    similarity_score=0.5,  # Fallback doesn't provide real similarity
                ))

            logger.info(f"Few-shot fallback search: found {len(examples)} examples")
            return examples

        except Exception as e:
            logger.error(f"Few-shot fallback search failed: {e}")
            return []

    async def add_example(
        self,
        question: str,
        answer: str,
        *,
        tenant_id: Optional[UUID] = None,
        category: Optional[str] = None,
        domain: Optional[FewShotDomain] = None,
        tags: Optional[List[str]] = None,
        quality_score: float = 1.0,
    ) -> Optional[UUID]:
        """Add a new few-shot example via Main API."""
        embedding = await self._get_embedding(question)

        try:
            client = await self._get_http_client()
            headers = {
                "X-API-Key": settings.MICROSERVICES_API_KEY,
            }
            if tenant_id:
                headers["X-Tenant-ID"] = str(tenant_id)

            payload: Dict[str, Any] = {
                "question": question,
                "answer": answer,
                "category": category,
                "domain": domain.value if domain and hasattr(domain, "value") else domain,
                "tags": tags,
                "quality_score": quality_score,
            }
            if embedding:
                payload["embedding"] = embedding

            response = await client.post(
                f"{settings.api_url}/api/v1/prompts/few-shot",
                json=payload,
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                example_id = UUID(data["id"])
                logger.info(f"Added few-shot example {example_id}")
                return example_id

            logger.warning(f"Failed to add few-shot example: HTTP {response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Failed to add few-shot example: {e}")
            return None

    async def update_usage(self, example_id: UUID) -> None:
        """Increment usage count via Main API feedback endpoint."""
        try:
            client = await self._get_http_client()
            await client.post(
                f"{settings.api_url}/api/v1/prompts/few-shot/{example_id}/feedback",
                params={"is_positive": True},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )
        except Exception as e:
            logger.debug(f"Failed to update usage count: {e}")

    async def submit_feedback(
        self,
        example_id: UUID,
        is_positive: bool,
    ) -> None:
        """Submit feedback via Main API."""
        try:
            client = await self._get_http_client()
            await client.post(
                f"{settings.api_url}/api/v1/prompts/few-shot/{example_id}/feedback",
                params={"is_positive": is_positive},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )
        except Exception as e:
            logger.error(f"Failed to submit feedback: {e}")

    def format_for_prompt(
        self,
        examples: List[FewShotExample],
        format_type: str = "qa",
    ) -> str:
        """Format examples for inclusion in a prompt."""
        if not examples:
            return ""

        lines = []
        lines.append("Ejemplos de referencia:")
        lines.append("")

        for i, ex in enumerate(examples, 1):
            if format_type == "qa":
                lines.append(f"Ejemplo {i}:")
                lines.append(f"P: {ex.question}")
                lines.append(f"R: {ex.answer}")
                lines.append("")
            elif format_type == "chat":
                lines.append(f"Ejemplo {i}:")
                lines.append(f"Usuario: {ex.question}")
                lines.append(f"Asistente: {ex.answer}")
                lines.append("")
            elif format_type == "xml":
                lines.append(f"<example id=\"{i}\">")
                lines.append(f"  <question>{ex.question}</question>")
                lines.append(f"  <answer>{ex.answer}</answer>")
                lines.append("</example>")
                lines.append("")

        return "\n".join(lines).strip()

    async def close(self) -> None:
        """Clean up resources."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        self._http_client = None
        self._embedding_cache.clear()


# Singleton instance
_retriever: Optional[FewShotRetriever] = None


def get_few_shot_retriever() -> FewShotRetriever:
    """Get the singleton FewShotRetriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = FewShotRetriever()
    return _retriever
