"""
Few-Shot Retriever — Semantic search for Q&A examples using pgvector.

Retrieves relevant Q&A examples based on query similarity to inject
into prompts as few-shot examples, improving response consistency.

Uses BGE-M3 embeddings (1024 dimensions) via weaviate-service's embedding endpoint.

Usage:
    retriever = get_few_shot_retriever()
    examples = await retriever.search("¿Cuántos días de preaviso para despido?", limit=3)
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.schemas.prompts import FewShotExampleResponse, FewShotDomain

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
    Retriever for few-shot examples using pgvector similarity search.

    Uses weaviate-service's embedding endpoint for BGE-M3 embeddings,
    then queries PostgreSQL with pgvector for similarity search.
    """

    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None
        self._db_session = None
        self._embedding_cache: Dict[str, List[float]] = {}
        self._cache_max_size = 100

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def _get_db_session(self):
        """Get async database session factory."""
        if self._db_session is None:
            try:
                from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
                from sqlalchemy.orm import sessionmaker

                engine = create_async_engine(settings.database_url)
                self._db_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            except Exception as e:
                logger.error(f"Failed to create DB session: {e}")
                return None
        return self._db_session

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding for text using weaviate-service.

        Uses the /embed endpoint which provides BGE-M3 embeddings.
        """
        # Check cache
        cache_key = text[:200]  # Truncate for cache key
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        try:
            client = await self._get_http_client()
            response = await client.post(
                f"{settings.weaviate_service_url}/embed",
                json={"text": text},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )

            if response.status_code == 200:
                data = response.json()
                embedding = data.get("embedding")
                if embedding:
                    # Cache the result
                    if len(self._embedding_cache) >= self._cache_max_size:
                        # Remove oldest entry (simple FIFO)
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
        Search for similar few-shot examples.

        Args:
            query: The query to find similar examples for
            limit: Maximum number of examples to return
            tenant_id: Filter by tenant (also includes global examples)
            domain: Filter by domain (legal, medical, documental)
            category: Filter by category
            min_quality_score: Minimum quality score threshold
            min_similarity: Minimum similarity threshold (default from settings)

        Returns:
            List of FewShotExample sorted by similarity (descending)
        """
        if not settings.few_shot_enabled:
            return []

        if min_similarity is None:
            min_similarity = settings.few_shot_min_similarity

        start_time = time.time()

        # Get embedding for query
        embedding = await self._get_embedding(query)
        if embedding is None:
            logger.warning("Could not get embedding for query, skipping few-shot retrieval")
            return []

        session_factory = await self._get_db_session()
        if not session_factory:
            return []

        try:
            from sqlalchemy import text

            async with session_factory() as session:
                # Build the query with pgvector cosine similarity
                # NOTE: This assumes pgvector extension is installed
                query_sql = text("""
                    SELECT
                        id, tenant_id, question, answer, category, domain, tags,
                        quality_score, usage_count, positive_feedback, negative_feedback,
                        is_active, created_at, updated_at,
                        1 - (embedding_vector <=> :embedding::vector) as similarity
                    FROM emma_few_shot_examples
                    WHERE is_active = true
                      AND embedding_vector IS NOT NULL
                      AND quality_score >= :min_quality
                      AND (tenant_id = :tenant_id OR tenant_id IS NULL)
                      AND (:domain IS NULL OR domain = :domain)
                      AND (:category IS NULL OR category = :category)
                    ORDER BY embedding_vector <=> :embedding::vector
                    LIMIT :limit
                """)

                # Format embedding as pgvector string
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

                result = await session.execute(
                    query_sql,
                    {
                        "embedding": embedding_str,
                        "tenant_id": str(tenant_id) if tenant_id else None,
                        "domain": domain.value if domain else None,
                        "category": category,
                        "min_quality": min_quality_score,
                        "limit": limit * 2,  # Fetch more for filtering
                    },
                )
                rows = result.fetchall()

                examples = []
                for row in rows:
                    similarity = row[14] if row[14] is not None else 0.0

                    # Filter by minimum similarity
                    if similarity < min_similarity:
                        continue

                    examples.append(FewShotExample(
                        id=row[0],
                        question=row[2],
                        answer=row[3],
                        category=row[4],
                        domain=row[5],
                        tags=row[6],
                        quality_score=row[7] or 1.0,
                        similarity_score=similarity,
                    ))

                    if len(examples) >= limit:
                        break

                elapsed_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"🔍 Few-shot search: found {len(examples)} examples "
                    f"(query_len={len(query)}, time={elapsed_ms:.1f}ms)"
                )

                return examples

        except Exception as e:
            logger.error(f"Few-shot search failed: {e}")
            # Try fallback without pgvector (keyword-based)
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
        """Fallback keyword-based search when pgvector is unavailable."""
        session_factory = await self._get_db_session()
        if not session_factory:
            return []

        try:
            from sqlalchemy import text

            # Extract keywords from query
            keywords = [w.lower() for w in query.split() if len(w) > 3]

            async with session_factory() as session:
                # Simple LIKE-based search
                query_sql = text("""
                    SELECT
                        id, tenant_id, question, answer, category, domain, tags,
                        quality_score, usage_count, positive_feedback, negative_feedback,
                        is_active, created_at, updated_at
                    FROM emma_few_shot_examples
                    WHERE is_active = true
                      AND quality_score >= :min_quality
                      AND (tenant_id = :tenant_id OR tenant_id IS NULL)
                      AND (:domain IS NULL OR domain = :domain)
                      AND (:category IS NULL OR category = :category)
                      AND LOWER(question) LIKE ANY(:keywords)
                    ORDER BY quality_score DESC, usage_count DESC
                    LIMIT :limit
                """)

                keyword_patterns = [f"%{kw}%" for kw in keywords[:5]]  # Limit keywords

                result = await session.execute(
                    query_sql,
                    {
                        "tenant_id": str(tenant_id) if tenant_id else None,
                        "domain": domain.value if domain else None,
                        "category": category,
                        "min_quality": min_quality_score,
                        "keywords": keyword_patterns,
                        "limit": limit,
                    },
                )
                rows = result.fetchall()

                examples = []
                for row in rows:
                    examples.append(FewShotExample(
                        id=row[0],
                        question=row[2],
                        answer=row[3],
                        category=row[4],
                        domain=row[5],
                        tags=row[6],
                        quality_score=row[7] or 1.0,
                        similarity_score=0.5,  # Fallback doesn't provide real similarity
                    ))

                logger.info(f"🔍 Few-shot fallback search: found {len(examples)} examples")
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
        """
        Add a new few-shot example with auto-generated embedding.

        Returns the ID of the created example, or None if failed.
        """
        # Get embedding for the question
        embedding = await self._get_embedding(question)

        session_factory = await self._get_db_session()
        if not session_factory:
            return None

        try:
            from sqlalchemy import text

            async with session_factory() as session:
                # Insert example
                if embedding:
                    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                    query_sql = text("""
                        INSERT INTO emma_few_shot_examples
                            (tenant_id, question, answer, category, domain, tags,
                             quality_score, embedding_vector)
                        VALUES
                            (:tenant_id, :question, :answer, :category, :domain, :tags,
                             :quality_score, :embedding::vector)
                        RETURNING id
                    """)
                else:
                    query_sql = text("""
                        INSERT INTO emma_few_shot_examples
                            (tenant_id, question, answer, category, domain, tags, quality_score)
                        VALUES
                            (:tenant_id, :question, :answer, :category, :domain, :tags, :quality_score)
                        RETURNING id
                    """)

                params = {
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "question": question,
                    "answer": answer,
                    "category": category,
                    "domain": domain.value if domain else None,
                    "tags": tags,
                    "quality_score": quality_score,
                }
                if embedding:
                    params["embedding"] = embedding_str

                result = await session.execute(query_sql, params)
                row = result.fetchone()
                await session.commit()

                example_id = row[0] if row else None
                if example_id:
                    logger.info(f"✅ Added few-shot example {example_id}")
                return example_id

        except Exception as e:
            logger.error(f"Failed to add few-shot example: {e}")
            return None

    async def update_usage(self, example_id: UUID) -> None:
        """Increment usage count for an example."""
        session_factory = await self._get_db_session()
        if not session_factory:
            return

        try:
            from sqlalchemy import text

            async with session_factory() as session:
                await session.execute(
                    text("""
                        UPDATE emma_few_shot_examples
                        SET usage_count = usage_count + 1, updated_at = now()
                        WHERE id = :id
                    """),
                    {"id": str(example_id)},
                )
                await session.commit()

        except Exception as e:
            logger.error(f"Failed to update usage count: {e}")

    async def submit_feedback(
        self,
        example_id: UUID,
        is_positive: bool,
    ) -> None:
        """Submit feedback for an example (updates quality score)."""
        session_factory = await self._get_db_session()
        if not session_factory:
            return

        try:
            from sqlalchemy import text

            async with session_factory() as session:
                if is_positive:
                    query = text("""
                        UPDATE emma_few_shot_examples
                        SET positive_feedback = positive_feedback + 1,
                            quality_score = LEAST(1.0, quality_score + 0.02),
                            updated_at = now()
                        WHERE id = :id
                    """)
                else:
                    query = text("""
                        UPDATE emma_few_shot_examples
                        SET negative_feedback = negative_feedback + 1,
                            quality_score = GREATEST(0.0, quality_score - 0.05),
                            updated_at = now()
                        WHERE id = :id
                    """)

                await session.execute(query, {"id": str(example_id)})
                await session.commit()

                logger.info(f"📊 Feedback recorded for example {example_id}: {'👍' if is_positive else '👎'}")

        except Exception as e:
            logger.error(f"Failed to submit feedback: {e}")

    def format_for_prompt(
        self,
        examples: List[FewShotExample],
        format_type: str = "qa",
    ) -> str:
        """
        Format examples for inclusion in a prompt.

        Args:
            examples: List of FewShotExample objects
            format_type: How to format examples
                - "qa": Q: ... A: ... format
                - "chat": User: ... Assistant: ... format
                - "xml": <example> tags format

        Returns:
            Formatted string ready for prompt injection
        """
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
        self._db_session = None
        self._embedding_cache.clear()


# Singleton instance
_retriever: Optional[FewShotRetriever] = None


def get_few_shot_retriever() -> FewShotRetriever:
    """Get the singleton FewShotRetriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = FewShotRetriever()
    return _retriever
