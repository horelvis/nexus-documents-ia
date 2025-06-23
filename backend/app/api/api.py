# app/api/api.py

from app.api.v1 import (
    document_insights, documents, document_shares, document_categorization, tenants, stripe, auth, admin, chat,
    agents, signatures, webhooks, search, teams, langgraph, users, entities, dashboard
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
api_router.include_router(document_shares.router, prefix="/shares", tags=["document-shares"])
api_router.include_router(document_categorization.router, prefix="/categorization", tags=["categorization"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(document_insights.router, prefix="/document-insights", tags=["document-insights"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])

# AI Agents and Digital Signature routes
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(signatures.router, prefix="/signatures", tags=["signatures"])

# AI-powered signature placement
from app.api.v1 import signature_ai
api_router.include_router(signature_ai.router, prefix="/signatures/ai", tags=["signature-ai"])

# Webhooks for external integrations
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])

# Teams management routes
api_router.include_router(teams.router, prefix="/teams", tags=["teams"])

# User management routes
api_router.include_router(users.router, prefix="/users", tags=["users"])

# LangGraph routes for advanced workflows
api_router.include_router(langgraph.router, prefix="/langgraph", tags=["langgraph"])

# Entity search and management
api_router.include_router(entities.router, tags=["entities"])

# Dashboard and analytics
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])