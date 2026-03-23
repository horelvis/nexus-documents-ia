"""DEPRECATED: This module will be removed. Memory recall should use
Weaviate hybrid search instead of pgvector.

MemoRAG service: memorize and recall using pgvector.
"""

import logging
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from .memory_store import MemoRAGStore

logger = logging.getLogger(__name__)


@dataclass
class RecallItem:
    document_id: str
    content: str
    similarity: float
    metadata: Dict[str, Any]


class MemoRAGService:
    def __init__(self) -> None:
        self._store = MemoRAGStore()
        self._http_client: Optional[httpx.AsyncClient] = None
        self._embedding_cache: Dict[str, List[float]] = {}
        self._cache_max_size = 200

    async def initialize(self) -> None:
        warnings.warn(
            "MemoRAG pgvector is deprecated. Use Weaviate hybrid search.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self._store.initialize()

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def _get_embedding(self, text: str, task: str) -> Optional[List[float]]:
        cache_key = f"{task}:{text[:200]}"
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        try:
            client = await self._get_http_client()
            response = await client.post(
                f"{settings.weaviate_service_url}/embed",
                json={"text": text, "task": task},
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

            logger.warning(f"MemoRAG embedding failed: {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"MemoRAG embedding error: {e}")
            return None

    @staticmethod
    def _chunk_text(text: str, chunk_size: int, overlap: int, max_chunks: int) -> List[str]:
        if not text:
            return []

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        def flush() -> None:
            nonlocal current, current_len
            if current:
                chunk = "\n\n".join(current).strip()
                if chunk:
                    chunks.append(chunk)
            current = []
            current_len = 0

        for paragraph in paragraphs:
            if current_len + len(paragraph) + 2 <= chunk_size:
                current.append(paragraph)
                current_len += len(paragraph) + 2
            else:
                flush()
                if len(paragraph) > chunk_size:
                    # Hard split long paragraph
                    start = 0
                    while start < len(paragraph):
                        end = min(start + chunk_size, len(paragraph))
                        chunk = paragraph[start:end]
                        chunks.append(chunk)
                        if len(chunks) >= max_chunks:
                            return chunks[:max_chunks]
                        start = max(0, end - overlap)
                else:
                    current.append(paragraph)
                    current_len = len(paragraph)

            if len(chunks) >= max_chunks:
                return chunks[:max_chunks]

        flush()

        # Add overlap between chunks for continuity
        if overlap > 0 and len(chunks) > 1:
            overlapped: List[str] = []
            for idx, chunk in enumerate(chunks):
                if idx == 0:
                    overlapped.append(chunk)
                    continue
                prefix = chunks[idx - 1]
                prefix = prefix[-overlap:] if len(prefix) > overlap else prefix
                overlapped.append((prefix + "\n" + chunk).strip())
            chunks = overlapped

        return chunks[:max_chunks]

    async def memorize(
        self,
        tenant_id: str,
        document_id: str,
        document_text: str,
        filename: str = "",
        domain: str = "",
        semantic_type: str = "",
    ) -> Dict[str, Any]:
        if not document_text or len(document_text.strip()) < settings.memorag_min_text_chars:
            return {"success": False, "error": "document_text too short"}

        await self.initialize()

        content_hash = self._store.hash_text(document_text)
        existing_hash = await self._store.document_hash(tenant_id, document_id)
        if existing_hash == content_hash:
            return {"success": True, "skipped": True, "document_id": document_id}

        chunks = self._chunk_text(
            document_text,
            chunk_size=settings.memorag_chunk_size,
            overlap=settings.memorag_chunk_overlap,
            max_chunks=settings.memorag_max_chunks,
        )

        if not chunks:
            return {"success": False, "error": "no chunks produced"}

        embeddings: List[List[float]] = []
        for chunk in chunks:
            embedding = await self._get_embedding(chunk[:settings.memorag_embed_text_max_chars], task=settings.memorag_embedding_task_document)
            if embedding is None:
                return {"success": False, "error": "embedding failed"}
            embeddings.append(embedding)

        metadata = {
            "filename": filename,
            "domain": domain or None,
            "semantic_type": semantic_type or None,
        }

        try:
            await self._store.replace_document_chunks(
                tenant_id=tenant_id,
                document_id=document_id,
                chunks=chunks,
                embeddings=embeddings,
                metadata=metadata,
                content_hash=content_hash,
                memory_version=settings.memorag_memory_version,
            )
        except Exception as e:
            logger.warning(f"MemoRAG store failed for {document_id}: {e}")
            return {"success": False, "error": str(e)}

        return {"success": True, "document_id": document_id, "chunks": len(chunks)}

    async def recall(
        self,
        tenant_id: str,
        query: str,
        limit: int = 20,
        domain: Optional[str] = None,
        semantic_type: Optional[str] = None,
    ) -> List[RecallItem]:
        await self.initialize()

        embedding = await self._get_embedding(query, task=settings.memorag_embedding_task_query)
        if embedding is None:
            return []

        rows = await self._store.recall(
            tenant_id=tenant_id,
            embedding=embedding,
            limit=limit,
            domain=domain,
            semantic_type=semantic_type,
        )

        if not rows and settings.memorag_keyword_fallback_enabled:
            rows = await self._store.keyword_recall(
                tenant_id=tenant_id,
                query=query[:200],
                limit=limit,
                domain=domain,
                semantic_type=semantic_type,
            )

        return [
            RecallItem(
                document_id=row.document_id,
                content=row.content,
                similarity=row.similarity,
                metadata=row.metadata,
            )
            for row in rows
        ]


_memorag_service: Optional[MemoRAGService] = None


def get_memorag_service() -> MemoRAGService:
    global _memorag_service
    if _memorag_service is None:
        _memorag_service = MemoRAGService()
    return _memorag_service
