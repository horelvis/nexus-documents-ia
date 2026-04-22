"""MemoRAG service — recall via Weaviate hybrid search.

Memorization is no longer needed: documents are already indexed in Weaviate
by the standard indexing pipeline.  Recall delegates to Weaviate hybrid
search (BM25 + vector), which is superior to the old vector-only approach.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RecallItem:
    document_id: str
    content: str
    similarity: float
    metadata: Dict[str, Any]


class MemoRAGService:
    """Thin wrapper that redirects recall to Weaviate hybrid search."""

    async def recall(
        self,
        query: str,
        user_roles: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        limit: int = 20,
        semantic_type: Optional[str] = None,
    ) -> List[RecallItem]:
        """Recall relevant document chunks via Weaviate hybrid search."""
        try:
            from app.clients.weaviate_client import get_weaviate_client

            client = get_weaviate_client()
            results = await client.hybrid_search(
                query=query,
                user_roles=user_roles or [],
                user_id=user_id,
                limit=limit,
                alpha=0.5,
                semantic_type_filter=semantic_type,
            )

            return [
                RecallItem(
                    document_id=r.metadata.get("document_id", r.document_id),
                    content=r.content,
                    similarity=r.score,
                    metadata=r.metadata,
                )
                for r in results
            ]
        except Exception as e:
            logger.warning(f"MemoRAG recall via Weaviate failed: {e}")
            return []

    async def memorize(
        self,
        document_id: str,
        document_text: str,
        filename: str = "",
        semantic_type: str = "",
    ) -> Dict[str, Any]:
        """No-op: documents are already indexed in Weaviate by the indexing pipeline."""
        logger.debug(
            "MemoRAG memorize() is a no-op — document %s is indexed via Weaviate pipeline",
            document_id,
        )
        return {"success": True, "skipped": True, "document_id": document_id}


_memorag_service: Optional[MemoRAGService] = None


def get_memorag_service() -> MemoRAGService:
    global _memorag_service
    if _memorag_service is None:
        _memorag_service = MemoRAGService()
    return _memorag_service
