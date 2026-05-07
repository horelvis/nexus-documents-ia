from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.search import router as search_router
from app.api.v1.signatures import router as signatures_router
from app.api.v1.signature_ai import router as signature_ai_router
from app.api.v1.signature_contacts import router as signature_contacts_router
from app.api.v1.entities import router as entities_router
from app.api.v1.analysis_queue import router as analysis_queue_router
from app.api.v1.channels import router as channels_router
from app.api.v1.emma import router as emma_router

# Import all modules needed by api.py
from app.api.v1 import (
    document_insights, documents, document_categorization, auth, admin,
    signatures, webhooks, search, users, entities, dashboard,
    analysis_queue, channels, gemini_voice,
    site_guests, site_portal, emma,
)
# Not yet implemented (SaaS-only):
# from app.api.v1.workflows import router as workflows_router
# from app.api.v1 import stripe, chat, assistant, workflows

__all__ = [
    "admin_router",
    "auth_router",
    "documents_router",
    "search_router",
    "signatures_router",
    "signature_ai_router",
    "signature_contacts_router",
    "entities_router",
    "analysis_queue_router",
    "channels_router",
    "emma_router",
]
