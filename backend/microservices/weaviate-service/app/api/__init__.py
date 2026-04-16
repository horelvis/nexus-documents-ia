"""API routers for Weaviate service (Vector Search & Indexing)"""

from .weaviate import router as weaviate_router
from .knowledge import router as knowledge_router

__all__ = [
    "weaviate_router",
    "knowledge_router",
]
