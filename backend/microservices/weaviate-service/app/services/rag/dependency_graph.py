"""
Dependency Graph for Hierarchical RAG

DEPRECATED: This module previously used Apache AGE for document structure
storage (sections, chunks, adjacency). Graph operations are now handled
by knowledge-tree-service (FalkorDB).

This stub preserves the public interface for backwards compatibility.
All methods return empty/no-op results. Callers should migrate to
knowledge-tree-service HTTP endpoints.

TODO: Remove this stub once all callers are migrated.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChunkExpansion:
    """Result of expanding a chunk's context."""
    chunk_id: str
    document_title: str
    section_hierarchy: List[str]
    adjacent_chunks: List[Dict[str, Any]]
    referenced_chunks: List[Dict[str, Any]]
    citing_documents: List[Dict[str, Any]]


class DependencyGraphService:
    """
    Dependency Graph Service for Hierarchical RAG (stub).

    Graph operations have been migrated to knowledge-tree-service.
    This class is a no-op stub preserving the interface.
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        logger.info(
            "DependencyGraphService is a no-op stub. "
            "Use knowledge-tree-service for graph operations."
        )

    async def index_document_structure(self, **kwargs) -> bool:
        logger.debug("dependency_graph.index_document_structure is a no-op stub")
        return False

    async def add_chunk_reference(self, **kwargs) -> bool:
        return False

    async def add_document_citation(self, **kwargs) -> bool:
        return False

    async def expand_chunk_context(self, chunk_id: str, **kwargs) -> Optional[ChunkExpansion]:
        return None

    async def get_document_graph_preview(self, **kwargs) -> Dict[str, Any]:
        return {"nodes": [], "edges": []}

    async def delete_document_graph(self, **kwargs) -> bool:
        return False

    async def close(self) -> None:
        pass


# Global singleton instance (no-op)
dependency_graph = DependencyGraphService()
