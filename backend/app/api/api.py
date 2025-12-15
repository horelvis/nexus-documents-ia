# app/api/api.py

from app.api.v1 import (
    document_insights, documents, document_shares, document_categorization, tenants, stripe, auth, admin, chat,
    agents, signatures, webhooks, search, teams, users, entities, dashboard,
    assistant, migration, weaviate, lgpd, workflows, analysis_queue, channels,
    internal_template_edit_sessions, internal_google_drive_tokens, google_drive,
    document_acl, folders, classification, site_guests, site_portal,
)
from fastapi import APIRouter


api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
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
api_router.include_router(google_drive.router)

# AI Agents and Digital Signature routes
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
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

internal_router = APIRouter(prefix="/internal", tags=["internal"])
internal_router.include_router(
    internal_template_edit_sessions.router,
    prefix="/template-edit-sessions",
    tags=["internal-template-edit-sessions"],
)
internal_router.include_router(
    internal_google_drive_tokens.router,
    prefix="/google-drive-tokens",
    tags=["internal-google-drive-tokens"],
)
api_router.include_router(internal_router)

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

# LGPD Compliance - User data deletion for Brazilian LGPD law
api_router.include_router(lgpd.router, prefix="/lgpd", tags=["lgpd"])

# Workflow Management - Camunda BPM integration
api_router.include_router(workflows.router, tags=["workflows"])

# Analysis Queue - Emma AI document analysis queue
api_router.include_router(analysis_queue.router, prefix="/analysis", tags=["analysis-queue"])

# Emma Voice Mode - Gemini Live API integration
from app.api.v1 import gemini_voice
api_router.include_router(gemini_voice.router, prefix="/gemini", tags=["gemini-voice"])

# TTS Service - Text-to-Speech for Emma Chat responses
from app.api.v1 import tts
api_router.include_router(tts.router, prefix="/tts", tags=["tts"])

# Information Channels - Gmail, Google Drive, External DB for RAG
api_router.include_router(channels.router, prefix="/channels", tags=["channels"])

# Document ACL - Document-level Access Control Lists
api_router.include_router(document_acl.router, prefix="/documents", tags=["document-acl"])

# Folders - Document folder organization (physical folders in GCS)
api_router.include_router(folders.router, prefix="/folders", tags=["folders"])

# Classification - RAG + LLM auto-classification system
api_router.include_router(classification.router, prefix="/classification", tags=["classification"])

# Site Guests - External sharing (admin management)
api_router.include_router(site_guests.router, prefix="/site-guests", tags=["site-guests"])

# Site Portal - External sharing (public guest access)
api_router.include_router(site_portal.router, prefix="/site-portal", tags=["site-portal"])

# Document Analyzer - CAG-based document analysis
# api_router.include_router(document_analyzer.router, prefix="/analyzer", tags=["document-analyzer"])

# Contract Intelligence - AI-powered contract analysis
# api_router.include_router(contract_intelligence.router, prefix="/contracts", tags=["contract-intelligence"])

# Compliance Checker - Regulatory compliance verification
# api_router.include_router(compliance_checker.router, prefix="/compliance", tags=["compliance-checker"])
