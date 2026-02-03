"""API routers for Emma Agent Service"""

from .emma import router as emma_router
from .learning import router as learning_router
from .uploads import router as uploads_router
from .verified_generation import router as verified_router
from .predictive_analysis import router as predictive_router
from .training import router as training_router
from .background import router as background_router
from .triggers import router as triggers_router
from .notifications import router as notifications_router
from .channels_emma import router as channels_router
from .heartbeat import router as heartbeat_router

__all__ = [
    "emma_router",
    "learning_router",
    "uploads_router",
    "verified_router",
    "predictive_router",
    "training_router",
    "background_router",
    "triggers_router",
    "notifications_router",
    "channels_router",
    "heartbeat_router",
]
