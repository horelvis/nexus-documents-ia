# app/api/api.py

from app.api.v1 import document_insights, documents, tenants, stripe, auth, admin, chat # Keep existing imports if they are structured differently
from fastapi import APIRouter


api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(stripe.router, prefix="/stripe", tags=["stripe"]) # Added stripe router
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(document_insights.router, prefix="/document-insights", tags=["document-insights"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])