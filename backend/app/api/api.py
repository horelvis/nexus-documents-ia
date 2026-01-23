# app/api/api.py
"""
API Router configuration with feature flag support.

Routes are conditionally included based on deployment mode and feature flags.
See app.core.features for configuration details.

Deployment modes:
- SAAS: All features enabled (default)
- ON_PREMISE: Emma-centric, SSO, connectors only
- CUSTOM: Individual feature control via env vars
"""

from app.api.v1 import (
    document_insights, documents, document_shares, document_categorization, tenants, auth, admin, chat,
    agents, webhooks, search, teams, users, entities,
    assistant, migration, weaviate, lgpd, workflows, analysis_queue, channels,
    internal_template_edit_sessions, internal_google_drive_tokens, google_drive,
    document_acl, folders, classification, sharing_insights,
)
from fastapi import APIRouter
from app.core.features import Feature, FeatureFlags
import logging

logger = logging.getLogger(__name__)

api_router = APIRouter()

# Log deployment mode at startup
logger.info(f"API starting in {FeatureFlags.get_deployment_mode()} mode")
logger.info(f"Enabled features: {FeatureFlags.get_enabled_features()}")

# === CORE ROUTES (Always enabled) ===
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

# === CONDITIONAL: SSO Multi-Protocol (On-premise) ===
if FeatureFlags.is_enabled(Feature.SSO_MULTI_PROTOCOL):
    from app.api.v1 import auth_sso
    api_router.include_router(auth_sso.router, prefix="/auth", tags=["sso-auth"])
    logger.debug("SSO multi-protocol routes enabled")

# Stripe billing (conditional)
if FeatureFlags.is_enabled(Feature.STRIPE_BILLING):
    from app.api.v1 import stripe
    api_router.include_router(stripe.router, prefix="/stripe", tags=["stripe"])
    logger.debug("Stripe billing routes enabled")
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(document_shares.router, prefix="/shares", tags=["document-shares"])
api_router.include_router(document_categorization.router, prefix="/categorization", tags=["categorization"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(document_insights.router, prefix="/document-insights", tags=["document-insights"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(assistant.router, tags=["assistant"])
api_router.include_router(google_drive.router)

# AI Agents (always enabled - core Emma functionality)
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])

# === CONDITIONAL: Digital Signatures ===
if FeatureFlags.is_enabled(Feature.DIGITAL_SIGNATURES):
    from app.api.v1 import signatures, signature_ai, signature_contacts
    api_router.include_router(signatures.router, prefix="/signatures", tags=["signatures"])
    api_router.include_router(signature_ai.router, prefix="/signatures/ai", tags=["signature-ai"])
    api_router.include_router(signature_contacts.router, prefix="/signatures/contacts", tags=["signature-contacts"])
    logger.debug("Digital signatures routes enabled")

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

# Internal connectors API for SIL reindex service
from app.api.v1 import internal_connectors
internal_router.include_router(
    internal_connectors.router,
    prefix="/connectors",
    tags=["internal-connectors"],
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

# === CONDITIONAL: Dashboard and analytics ===
if FeatureFlags.is_enabled(Feature.DASHBOARD_ANALYTICS):
    from app.api.v1 import dashboard
    api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
    logger.debug("Dashboard analytics routes enabled")

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

# NexusLM - NotebookLM-style document notebooks with podcast generation
from app.api.v1 import notebooks
api_router.include_router(notebooks.router, prefix="/notebooks", tags=["notebooks"])

# Information Channels - Gmail, Google Drive, External DB for RAG
api_router.include_router(channels.router, prefix="/channels", tags=["channels"])

# Document ACL - Document-level Access Control Lists
api_router.include_router(document_acl.router, prefix="/documents", tags=["document-acl"])

# Folders - Document folder organization (physical folders in GCS)
api_router.include_router(folders.router, prefix="/folders", tags=["folders"])

# Classification - RAG + LLM auto-classification system
api_router.include_router(classification.router, prefix="/classification", tags=["classification"])

# === CONDITIONAL: Site Portal (External sharing) ===
if FeatureFlags.is_enabled(Feature.SITE_PORTAL):
    from app.api.v1 import site_guests, site_portal
    api_router.include_router(site_guests.router, prefix="/site-guests", tags=["site-guests"])
    api_router.include_router(site_portal.router, prefix="/site-portal", tags=["site-portal"])
    logger.debug("Site portal routes enabled")

# Sharing Insights - Analytics for document sharing and site guests (Emma AI)
api_router.include_router(sharing_insights.router, tags=["sharing-insights"])

# Feature Flags - Expose feature state to frontend
from app.api.v1 import features
api_router.include_router(features.router)

# === CONNECTORS (On-premise data source management) ===
# These are always enabled as they're core to Emma's data access
from app.api.v1 import connectors, user_sync, data_learning
api_router.include_router(connectors.router, prefix="/connectors", tags=["connectors"])
api_router.include_router(user_sync.router, prefix="/user-sync", tags=["user-sync"])
logger.debug("Connector routes enabled")

# Data Learning System - Learn connector data nature for intelligent RAG
api_router.include_router(
    data_learning.router,
    prefix="/connectors",
    tags=["data-learning"]
)
logger.debug("Data Learning routes enabled")

# Document Analyzer - CAG-based document analysis
# api_router.include_router(document_analyzer.router, prefix="/analyzer", tags=["document-analyzer"])

# Contract Intelligence - AI-powered contract analysis
# api_router.include_router(contract_intelligence.router, prefix="/contracts", tags=["contract-intelligence"])

# Compliance Checker - Regulatory compliance verification
# api_router.include_router(compliance_checker.router, prefix="/compliance", tags=["compliance-checker"])
