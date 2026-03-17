"""API routers for Emma Agent Service"""

from .emma import router as emma_router
from .learning import router as learning_router
from .uploads import router as uploads_router
from .training import router as training_router
from .background import router as background_router
from .triggers import router as triggers_router
from .notifications import router as notifications_router
from .channels_emma import router as channels_router
from .heartbeat import router as heartbeat_router
from .prompts import router as prompts_router
from .diagnostics import router as diagnostics_router
from .generated_documents import router as generated_documents_router

__all__ = [
    "emma_router",
    "learning_router",
    "uploads_router",
    "training_router",
    "background_router",
    "triggers_router",
    "notifications_router",
    "channels_router",
    "heartbeat_router",
    "prompts_router",
    "diagnostics_router",
    "generated_documents_router",
]
