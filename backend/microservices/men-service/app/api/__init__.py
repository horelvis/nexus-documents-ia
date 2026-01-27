"""API routes for MEN service."""

from .routes import router as main_router
from .tenant_routes import router as tenant_router
from .session_routes import router as session_router

__all__ = ["main_router", "tenant_router", "session_router"]
