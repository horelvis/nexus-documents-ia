# app/api/api.py

from app.api.v1 import auth, document_insights, documents, tenants, admin
from fastapi import APIRouter


api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(document_insights.router, prefix="/document-insights", tags=["document-insights"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])