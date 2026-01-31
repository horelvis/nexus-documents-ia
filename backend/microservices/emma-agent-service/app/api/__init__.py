"""API routers for Emma Agent Service"""

from .emma import router as emma_router
from .learning import router as learning_router
from .uploads import router as uploads_router
from .verified_generation import router as verified_router

__all__ = [
    "emma_router",
    "learning_router",
    "uploads_router",
    "verified_router",
]
