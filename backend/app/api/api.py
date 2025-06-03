# app/api/api.py

from app.api.v1 import (
    document_insights, documents, tenants, stripe, auth, admin, chat,
    agents, signatures  # Added new routers
)
from fastapi import APIRouter


api_router = APIRouter()

# Log para verificar que se incluye el router de auth
import logging
logger = logging.getLogger(__name__)
logger.info("🔧 Including auth router with endpoints...")

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

logger.info("✅ Auth router included with prefix=/auth")
api_router.include_router(stripe.router, prefix="/stripe", tags=["stripe"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(document_insights.router, prefix="/document-insights", tags=["document-insights"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])

# AI Agents and Digital Signature routes
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(signatures.router, prefix="/signatures", tags=["signatures"])