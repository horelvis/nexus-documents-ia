# app/api/api.py

from app.api.v1 import (
    document_insights, documents, document_shares, document_categorization, tenants, stripe, auth, admin, chat,
    agents, agent_management, signatures, webhooks, search, teams, users, entities, dashboard,
    simple_auth, assistant, migration, weaviate, bpmn_ai, lgpd
    # REMOVED: langgraph - migrated to Weaviate/Elysia
    # document_analyzer, contract_intelligence, compliance_checker
)
from fastapi import APIRouter


api_router = APIRouter()

# Log para verificar que se incluye el router de auth
import logging
logger = logging.getLogger(__name__)
logger.info("🔧 Including auth router with endpoints...")

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(simple_auth.router, prefix="/simple-auth", tags=["simple-auth"])

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
api_router.include_router(assistant.router, tags=["assistant"])

# AI Agents and Digital Signature routes
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(agent_management.router, prefix="/agent-management", tags=["agent-management"])
api_router.include_router(signatures.router, prefix="/signatures", tags=["signatures"])

# AI-powered signature placement
from app.api.v1 import signature_ai
api_router.include_router(signature_ai.router, prefix="/signatures/ai", tags=["signature-ai"])

# Signature contacts management
from app.api.v1 import signature_contacts
api_router.include_router(signature_contacts.router, prefix="/signatures/contacts", tags=["signature-contacts"])

# Webhooks for external integrations
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])

# Weaviate microservice gateway (includes Elysia)
api_router.include_router(weaviate.router, prefix="/weaviate", tags=["weaviate"])

# Teams management routes
api_router.include_router(teams.router, prefix="/teams", tags=["teams"])

# User management routes
api_router.include_router(users.router, prefix="/users", tags=["users"])

# REMOVED: LangGraph routes - migrated to Weaviate/Elysia
# api_router.include_router(langgraph.router, prefix="/langgraph", tags=["langgraph"])

# Entity search and management
api_router.include_router(entities.router, tags=["entities"])

# Dashboard and analytics
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])

# NEW: Migration management for Qdrant->Weaviate transition
api_router.include_router(migration.router, prefix="/migration", tags=["migration"])

# NEW: BPM AI - Business Process Management with AI
api_router.include_router(bpmn_ai.router, tags=["bpmn-ai"])

# LGPD Compliance - User data deletion for Brazilian LGPD law
api_router.include_router(lgpd.router, prefix="/lgpd", tags=["lgpd"])

# Document Analyzer - CAG-based document analysis
# api_router.include_router(document_analyzer.router, prefix="/analyzer", tags=["document-analyzer"])

# Contract Intelligence - AI-powered contract analysis
# api_router.include_router(contract_intelligence.router, prefix="/contracts", tags=["contract-intelligence"])

# Compliance Checker - Regulatory compliance verification
# api_router.include_router(compliance_checker.router, prefix="/compliance", tags=["compliance-checker"])