"""
Tenant Knowledge Service for Emma Agent

Provides tenant-specific knowledge and structural summaries via weaviate-service.
"""

import logging
from typing import Dict, Any, Optional, List
from functools import lru_cache

from app.clients import get_knowledge_tree_client

logger = logging.getLogger(__name__)


class TenantKnowledgeService:
    """
    Service for managing tenant-specific knowledge.

    This service provides access to tenant knowledge including:
    - Document structure summaries
    - Learned terminology
    - Entity relationships
    """

    def __init__(self):
        self._initialized = False
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        """Initialize the service."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ TenantKnowledgeService initialized")

    async def get_structural_summary(
        self,
        tenant_id: str,
        include_entities: bool = True,
        include_relationships: bool = False,
    ) -> str:
        """
        Get structural summary for a tenant.

        This provides learned terminology and document structure information
        that can be used to enhance query understanding.

        Args:
            tenant_id: Tenant identifier
            include_entities: Include named entities
            include_relationships: Include entity relationships

        Returns:
            Summary string with learned terminology and structure.
        """
        # Check cache first
        cache_key = f"{tenant_id}:{include_entities}:{include_relationships}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            client = get_knowledge_tree_client()

            # Get structural summary from knowledge-tree-service
            summary_resp = await client.get_structural_summary(
                tenant_id=tenant_id,
            )

            summary_text = ""
            if isinstance(summary_resp, dict):
                summary_text = summary_resp.get("summary", "")
            elif isinstance(summary_resp, str):
                summary_text = summary_resp

            # Cache the result
            self._cache[cache_key] = summary_text
            return summary_text

        except Exception as e:
            logger.warning(f"Failed to get structural summary for tenant {tenant_id}: {e}")
            return ""

    async def get_document_count(self, tenant_id: str) -> int:
        """Get total document count for tenant."""
        try:
            client = get_weaviate_client()
            stats = await client.get_tenant_stats(tenant_id)
            return stats.get("document_count", 0)
        except Exception as e:
            logger.warning(f"Failed to get document count: {e}")
            return 0

    async def get_tenant_schema(self, tenant_id: str) -> Dict[str, Any]:
        """Get schema information for tenant's documents."""
        try:
            client = get_weaviate_client()
            return await client.get_tenant_schema(tenant_id)
        except Exception as e:
            logger.warning(f"Failed to get tenant schema: {e}")
            return {"collections": [], "properties": {}}

    def clear_cache(self, tenant_id: Optional[str] = None):
        """Clear cached knowledge."""
        if tenant_id:
            keys_to_remove = [k for k in self._cache if k.startswith(tenant_id)]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            self._cache.clear()


# Singleton instance
_tenant_knowledge_service: Optional[TenantKnowledgeService] = None


def get_tenant_knowledge_service() -> TenantKnowledgeService:
    """Get or create the tenant knowledge service singleton."""
    global _tenant_knowledge_service
    if _tenant_knowledge_service is None:
        _tenant_knowledge_service = TenantKnowledgeService()
    return _tenant_knowledge_service


# Alias for compatibility
tenant_knowledge_service = get_tenant_knowledge_service()
