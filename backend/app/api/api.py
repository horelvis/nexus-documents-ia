# app/api/api.py

from app.api.v1.endpoints import auth, users # Assuming documents, tenants etc. are in endpoints too
from app.api.v1 import document_insights, documents, tenants, admin # Keep existing imports if they are structured differently
from fastapi import APIRouter


api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"]) # Added users router
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(document_insights.router, prefix="/document-insights", tags=["document-insights"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])