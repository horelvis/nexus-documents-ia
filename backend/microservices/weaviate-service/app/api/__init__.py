"""API routers for Weaviate service"""

from .weaviate import router as weaviate_router
from .elysia import router as elysia_router
from .public_knowledge import router as public_knowledge_router

__all__ = ["weaviate_router", "elysia_router", "public_knowledge_router"]