"""
Elasticsearch Client Stub

This is a no-op stub that replaces the original Elasticsearch client.
Elasticsearch has been replaced by Weaviate's hybrid search (BM25 + vector).

All methods return empty results or do nothing, allowing existing code
that checks elasticsearch_enabled() to continue working without errors.
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SearchUserContext:
    """User context for search operations (stub)."""
    user_id: str = ""
    roles: List[str] = None

    def __post_init__(self):
        if self.roles is None:
            self.roles = []


class ElasticsearchClientStub:
    """
    No-op Elasticsearch client stub.

    All methods log a warning and return empty results.
    This allows code with elasticsearch_enabled() checks to work
    without raising import errors.
    """

    _warned = False

    def _warn_once(self):
        if not self._warned:
            logger.warning(
                "⚠️ Elasticsearch is disabled. "
                "Using Weaviate hybrid search instead. "
                "This stub does nothing."
            )
            self._warned = True

    async def search(self, *args, **kwargs) -> Dict[str, Any]:
        """Search stub - returns empty results."""
        self._warn_once()
        return {"hits": {"total": {"value": 0}, "hits": []}}

    async def index_document(self, *args, **kwargs) -> bool:
        """Index stub - does nothing."""
        self._warn_once()
        return True

    async def delete_document(self, *args, **kwargs) -> bool:
        """Delete stub - does nothing."""
        self._warn_once()
        return True

    async def update_document(self, *args, **kwargs) -> bool:
        """Update stub - does nothing."""
        self._warn_once()
        return True

    async def bulk_index(self, *args, **kwargs) -> Dict[str, Any]:
        """Bulk index stub - does nothing."""
        self._warn_once()
        return {"items": [], "errors": False}

    async def create_index(self, *args, **kwargs) -> bool:
        """Create index stub - does nothing."""
        self._warn_once()
        return True

    async def delete_index(self, *args, **kwargs) -> bool:
        """Delete index stub - does nothing."""
        self._warn_once()
        return True

    async def health_check(self) -> Dict[str, Any]:
        """Health check stub - returns disabled status."""
        return {
            "status": "disabled",
            "message": "Elasticsearch disabled - using Weaviate hybrid search"
        }

    def __getattr__(self, name):
        """Catch-all for any other method calls."""
        self._warn_once()
        async def noop(*args, **kwargs):
            return None
        return noop


# Global singleton stub
elasticsearch_client = ElasticsearchClientStub()
