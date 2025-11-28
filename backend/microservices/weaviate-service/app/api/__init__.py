"""API routers for Weaviate service"""

from .cag import router as cag_router
from .elysia import router as elysia_router
from .weaviate import router as weaviate_router

__all__ = ["weaviate_router", "elysia_router", "cag_router"]
