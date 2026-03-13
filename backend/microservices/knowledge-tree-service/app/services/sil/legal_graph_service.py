"""
DEPRECATED: Legal Graph Service Stub

This stub is superseded by app.services.legal_graph_service which
provides the real implementation using Apache AGE directly.
Use `from app.services.legal_graph_service import legal_graph` instead.

Kept temporarily for backwards compatibility with scripts.
"""

import logging
from typing import Dict, Any, List, Optional

from app.clients import get_weaviate_client

logger = logging.getLogger(__name__)


class LegalGraphService:
    """
    Legal Graph Service stub that delegates to weaviate-service.

    Provides access to legal knowledge graph for:
    - Legal concept relationships
    - Legislation references
    - Case law citations
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """Initialize the service."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ LegalGraphService stub initialized")

    async def search_legal_concepts(
        self,
        query: str,
        tenant_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search for legal concepts related to query."""
        try:
            client = get_weaviate_client()
            # Delegate to weaviate-service
            results = await client.search_documents(
                tenant_id=tenant_id,
                query=query,
                limit=limit,
                filters={"document_type": "legal"}
            )
            return [{"id": r.document_id, "content": r.content, "score": r.score} for r in results]
        except Exception as e:
            logger.warning(f"Legal concept search failed: {e}")
            return []

    async def get_related_legislation(
        self,
        concept: str,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """Get legislation related to a legal concept."""
        # Stub - returns empty list
        return []

    async def get_case_citations(
        self,
        document_id: str,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """Get case citations for a document."""
        # Stub - returns empty list
        return []


# Singleton instance
legal_graph_service = LegalGraphService()
