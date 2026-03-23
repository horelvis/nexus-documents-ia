"""MemoRAG service — recall via Weaviate hybrid search.

Memorization is no longer needed: documents are already indexed in Weaviate
by the standard indexing pipeline.  Recall delegates to Weaviate hybrid
search (BM25 + vector), which is superior to the old pgvector vector-only
approach.
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
        tenant_id: str,
        query: str,
        limit: int = 20,
        domain: Optional[str] = None,
        semantic_type: Optional[str] = None,
    ) -> List[RecallItem]:
        """Recall relevant document chunks via Weaviate hybrid search.

        Args:
            tenant_id: Tenant identifier.
            query: Natural-language query.
            limit: Maximum results to return.
            domain: Optional domain filter (legal, medical, ...).
            semantic_type: Optional semantic type filter (contrato, factura, ...).

        Returns:
            List[RecallItem] compatible with the old pgvector interface.
        """
        try:
            from app.clients.weaviate_client import get_weaviate_client

            client = get_weaviate_client()
            results = await client.hybrid_search(
                tenant_id=tenant_id,
                query=query,
                limit=limit,
                alpha=0.5,  # balanced hybrid
                domain_filter=domain,
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
        tenant_id: str,
        document_id: str,
        document_text: str,
        filename: str = "",
        domain: str = "",
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
