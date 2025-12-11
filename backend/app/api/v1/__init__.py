from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.document_shares import router as document_shares_router
from app.api.v1.document_acl import router as document_acl_router
from app.api.v1.search import router as search_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.signatures import router as signatures_router
from app.api.v1.signature_ai import router as signature_ai_router
from app.api.v1.signature_contacts import router as signature_contacts_router
from app.api.v1.entities import router as entities_router
from app.api.v1.workflows import router as workflows_router
from app.api.v1.analysis_queue import router as analysis_queue_router
from app.api.v1.channels import router as channels_router

# Import all modules needed by api.py
from app.api.v1 import (
    document_insights, documents, document_shares, document_acl, document_categorization, tenants, stripe, auth, admin, chat,
    agents, signatures, webhooks, search, teams, users, entities, dashboard,
    assistant, migration, workflows, analysis_queue, channels, gemini_voice
)
# from app.api.v1.document_analyzer import router as document_analyzer_router
# from app.api.v1.contract_intelligence import router as contract_intelligence_router
# from app.api.v1.compliance_checker import router as compliance_checker_router

# Optional: Define __all__ to specify what gets imported with 'from app.api.v1 import *'
# For clarity, it's often better to rely on specific imports as done in main.py,
# but __all__ can be good practice.
__all__ = [
    "admin_router",
    "auth_router",
    "documents_router",
    "document_shares_router",
    "document_acl_router",
    "search_router",
    "tenants_router",
    "signatures_router",
    "signature_ai_router",
    "signature_contacts_router",
    "entities_router",
    "workflows_router",
    "analysis_queue_router",
    "channels_router",
    # "document_analyzer_router",
    # "contract_intelligence_router",
    # "compliance_checker_router",
]
