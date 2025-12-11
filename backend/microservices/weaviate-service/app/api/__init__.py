"""API routers for Weaviate service"""

from .weaviate import router as weaviate_router
from .emma import router as emma_router
from .public_knowledge import router as public_knowledge_router

__all__ = ["weaviate_router", "emma_router", "public_knowledge_router"]
