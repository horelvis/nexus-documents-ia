"""API routers for Weaviate service (RAG & Vector Search)

Note: Emma and agent orchestration APIs have been moved
to emma-agent-service for independent scaling.
Note: Verified generation APIs have been moved
to emma-agent-service.
"""

from .weaviate import router as weaviate_router
from .public_knowledge import router as public_knowledge_router
from .knowledge import router as knowledge_router
from .learning import router as learning_router

__all__ = [
    "weaviate_router",
    "public_knowledge_router",
    "knowledge_router",
    "learning_router",
]
